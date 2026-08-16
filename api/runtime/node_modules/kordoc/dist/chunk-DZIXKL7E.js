#!/usr/bin/env node

// src/redact.ts
var DEFAULT_REDACT_RULES = [
  "rrn",
  "phone",
  "email",
  "card",
  "account"
];
var RULE_PRIORITY = [
  "rrn",
  "email",
  "card",
  "phone",
  "driver",
  "account",
  "passport"
];
function luhnValid(digits) {
  let sum = 0;
  for (let i = 0; i < digits.length; i++) {
    let d = digits.charCodeAt(digits.length - 1 - i) - 48;
    if (i % 2 === 1) {
      d *= 2;
      if (d > 9) d -= 9;
    }
    sum += d;
  }
  return sum % 10 === 0;
}
function birthdateValid(front6) {
  const mm = Number(front6.slice(2, 4));
  const dd = Number(front6.slice(4, 6));
  return mm >= 1 && mm <= 12 && dd >= 1 && dd <= 31;
}
var RULES = {
  // 주민/외국인등록번호 — 뒷자리 첫 숫자 1-8 + 생년월일 유효성으로 오탐 축소.
  // 유니코드 대시 변형(‐ ‑ – —)은 rrn만 허용. 앞 6자리 유지, 뒤 7자리 전부 마스크.
  rrn: {
    pattern: /(?<!\d)(\d{6})([-‐‑–—])([1-8]\d{6})(?!\d)/g,
    validate: (m) => birthdateValid(m[1]),
    mask: (m, mc) => m[1] + m[2] + mc.repeat(7)
  },
  // 이메일 — 로컬파트 첫 글자만 남기고 마스크, 도메인 유지
  email: {
    pattern: /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g,
    mask: (m, mc) => {
      const at = m[0].indexOf("@");
      return m[0][0] + mc.repeat(at - 1) + m[0].slice(at);
    }
  },
  // 카드번호 — 구분자 필수(무구분 16자리는 오탐 높아 제외), 동일 구분자 강제(\2),
  // Luhn 체크. 가운데 8자리 마스크.
  card: {
    pattern: /(?<!\d)(\d{4})([- ])(\d{4})\2(\d{4})\2(\d{4})(?!\d)/g,
    validate: (m) => luhnValid(m[1] + m[3] + m[4] + m[5]),
    mask: (m, mc) => m[1] + m[2] + mc.repeat(4) + m[2] + mc.repeat(4) + m[2] + m[5]
  },
  // 전화번호 — 휴대폰(01[016789])·서울(02)·지역(0[3-6]\d)·인터넷(070)은 구분자
  // -·.·공백 또는 무구분(동일 구분자 강제), 대표번호(15xx/16xx/18xx)는 구분자 필수.
  // 가운데 자리만 마스크 (대표번호는 뒤 4자리). 선행 [\d-] 금지 — 계좌 부분매치 방지.
  phone: {
    pattern: /(?<![\d-])(?:(01[016789]|070|02|0[3-6]\d)([-. ]?)(\d{3,4})\2(\d{4})|(1[568]\d{2})([-. ])(\d{4}))(?!\d)/g,
    mask: (m, mc) => m[1] !== void 0 ? m[1] + m[2] + mc.repeat(m[3].length) + m[2] + m[4] : m[5] + m[6] + mc.repeat(4)
  },
  // 운전면허 (기본 OFF) — 신형 12자리만 (지역명 2글자 선행 구버전은 스킵). 뒷 8자리 마스크.
  driver: {
    pattern: /(?<![\d-])(\d{2})-(\d{2})-\d{6}-\d{2}(?!-?\d)/g,
    mask: (m, mc) => m[1] + "-" + m[2] + "-" + mc.repeat(6) + "-" + mc.repeat(2)
  },
  // 계좌번호 — 3~4그룹 + 총 자릿수 10~16. rrn·card·phone과 겹치면 그쪽 우선.
  // 마지막 그룹 빼고 전부 마스크. 사업자등록번호(3-2-5, 10자리)도 걸린다 — 계약상 의도
  // (테스트로 명시). 날짜(2026-07-16)는 8자리라 총자릿수 검증에서 탈락.
  account: {
    pattern: /(?<!\d)(?<!\d-)\d{2,6}(?:-\d{2,6}){1,2}-\d{2,8}(?!-?\d)/g,
    validate: (m) => {
      const digits = m[0].replace(/-/g, "").length;
      return digits >= 10 && digits <= 16;
    },
    mask: (m, mc) => {
      const parts = m[0].split("-");
      return parts.map((p, i) => i === parts.length - 1 ? p : mc.repeat(p.length)).join("-");
    }
  },
  // 여권번호 (기본 OFF) — 단어 경계, 첫 글자만 남기고 전부 마스크
  passport: {
    pattern: /\b([MSRODG])\d{8}(?![0-9A-Za-z])/g,
    mask: (m, mc) => m[1] + mc.repeat(8)
  }
};
function redactText(text, options) {
  const maskChar = options?.maskChar ?? "\u25CF";
  if (maskChar.length !== 1 || /[0-9A-Za-z]/.test(maskChar)) {
    throw new Error(`maskChar\uB294 \uC601\uC22B\uC790\uAC00 \uC544\uB2CC 1\uAE00\uC790\uC5EC\uC57C \uD568: ${JSON.stringify(maskChar)}`);
  }
  const enabled = options?.rules ?? DEFAULT_REDACT_RULES;
  const hits = [];
  if (text === "" || enabled.length === 0) return { text, hits };
  const occupied = [];
  for (const rule of RULE_PRIORITY) {
    if (!enabled.includes(rule)) continue;
    const def = RULES[rule];
    for (const m of text.matchAll(def.pattern)) {
      if (def.validate && !def.validate(m)) continue;
      const start = m.index;
      const end = start + m[0].length;
      if (occupied.some((o) => start < o.end && end > o.start)) continue;
      occupied.push({ start, end });
      hits.push({ rule, masked: def.mask(m, maskChar), index: start, length: m[0].length });
    }
  }
  hits.sort((a, b) => a.index - b.index);
  let out = "";
  let cursor = 0;
  for (const h of hits) {
    out += text.slice(cursor, h.index) + h.masked;
    cursor = h.index + h.length;
  }
  out += text.slice(cursor);
  return { text: out, hits };
}
function redactMarkdown(markdown, options) {
  const lines = markdown.split("\n");
  const hits = [];
  let offset = 0;
  const outLines = lines.map((line) => {
    if (line.includes("data:image/")) {
      offset += line.length + 1;
      return line;
    }
    const r = redactText(line, options);
    for (const h of r.hits) hits.push({ ...h, index: h.index + offset });
    offset += line.length + 1;
    return r.text;
  });
  return { text: outLines.join("\n"), hits };
}

export {
  DEFAULT_REDACT_RULES,
  redactText,
  redactMarkdown
};
//# sourceMappingURL=chunk-DZIXKL7E.js.map