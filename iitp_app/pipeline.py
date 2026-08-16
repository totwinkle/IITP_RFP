from __future__ import annotations

import html
import re
from datetime import date


PLACEHOLDER = "[추가 결정 필요]"

FIELD_ALIASES = {
    "title": ("수요명", "품목명", "사업명", "과제명"),
    "classification": ("기술분야", "기술분류"),
    "period": ("총 기술개발 기간", "개발기간", "사업기간"),
    "budget": ("총 소요 금액", "정부출연금", "총사업비", "예산"),
    "objective": ("개발목표", "사업목표", "최종목표"),
    "contents": ("개발내용", "주요 연구내용", "주요 내용"),
    "trends": ("국내·외 기술개발 동향", "국내외 기술개발 동향", "주요동향"),
    "need": ("지원 필요성/기대효과", "지원 필요성", "필요성", "기대효과"),
}

REPORT_ITEMS = (
    "추진배경", "개념 및 범위", "사업 근거", "정책·산업·시장·기술 동향",
    "사업목표 및 범위", "주요 연구내용", "정부지원 필요성 및 시급성",
    "기존사업과 차별성", "사업 추진절차", "연차별 투자계획", "성과관리계획",
    "기대효과", "참고자료",
)


def clean_text(value: str) -> str:
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    value = re.sub(r"[*_`]", "", value)
    value = re.sub(r"[ \t]+", " ", value)
    return value.strip(" |\n")


def analyze_markdown(markdown: str) -> dict:
    fields = {}
    for key, aliases in FIELD_ALIASES.items():
        value, anchor = _find_field(markdown, aliases)
        fields[key] = {
            "value": value or PLACEHOLDER,
            "provenance": "source_input" if value else "unresolved",
            "source_anchor": anchor,
        }
    if fields["title"]["value"] == PLACEHOLDER:
        heading = next((clean_text(line.lstrip("# ")) for line in markdown.splitlines() if line.startswith("#") and clean_text(line.lstrip("# "))), None)
        fields["title"] = {"value": heading or "기술수요 기반 연구개발 사업", "provenance": "source_input" if heading else "generated_generic", "source_anchor": "first_heading" if heading else None}
    bullets = [clean_text(line) for line in markdown.splitlines() if re.match(r"^\s*(?:[-*]|ㅇ|○|□|◈)\s*", line)]
    mapping = []
    direct_by_item = {
        "추진배경": ("need", "trends"), "개념 및 범위": ("objective", "contents"),
        "사업 근거": (), "정책·산업·시장·기술 동향": ("trends",),
        "사업목표 및 범위": ("objective", "contents"), "주요 연구내용": ("contents",),
        "정부지원 필요성 및 시급성": ("need",), "기존사업과 차별성": (),
        "사업 추진절차": (), "연차별 투자계획": ("period", "budget"),
        "성과관리계획": (), "기대효과": ("need",), "참고자료": (),
    }
    decision_items = {"개념 및 범위", "사업목표 및 범위", "사업 추진절차", "연차별 투자계획", "성과관리계획", "기존사업과 차별성"}
    for item in REPORT_ITEMS:
        source_keys = [key for key in direct_by_item[item] if fields[key]["provenance"] == "source_input"]
        classification = []
        if source_keys:
            classification.append("direct")
        if item in {"사업 근거", "정책·산업·시장·기술 동향", "기존사업과 차별성"}:
            classification.append("research_needed")
        if item in decision_items:
            classification.append("decision_needed")
        if not classification:
            classification.append("research_needed")
        mapping.append({"report_item": item, "classification": classification, "source_fields": source_keys})
    questions = [
        {"key": "policy_priority", "question": "사업의 정책적 최우선 방향은 무엇입니까?"},
        {"key": "scope", "question": "포함 범위와 제외 범위를 어떻게 확정할까요?"},
        {"key": "structure", "question": "단일사업과 세부과제 구조 중 어떤 형태입니까?"},
        {"key": "period_budget", "question": "사업기간·총예산·연차 배분은 어떻게 확정할까요?"},
        {"key": "kpi", "question": "정량 KPI, 측정방법, 검증증적은 무엇입니까?"},
        {"key": "demonstration_trl", "question": "대표 실증대상·시험환경·목표 TRL은 무엇입니까?"},
    ]
    return {
        "fields": fields,
        "mapping": mapping,
        "questions": questions,
        "source_outline": [clean_text(line) for line in markdown.splitlines() if line.startswith("#")][:40],
        "source_bullets": bullets[:80],
        "warnings": ["외부 근거는 자동 추정하지 않았습니다. 출처 레지스트리에 직접 추가해 주세요."],
    }


def _find_field(markdown: str, aliases: tuple[str, ...]) -> tuple[str | None, str | None]:
    lines = markdown.splitlines()
    for index, line in enumerate(lines):
        if "|" in line:
            cells = [clean_text(cell) for cell in line.strip().strip("|").split("|")]
            if len(cells) >= 2 and any(alias == cells[0] or alias in cells[0] for alias in aliases):
                value = " | ".join(cell for cell in cells[1:] if cell and not re.fullmatch(r"-+", cell))
                if value:
                    return value, f"table-row:{index + 1}"
    for index, line in enumerate(lines):
        normalized = clean_text(line.lstrip("# "))
        if any(alias == normalized or normalized.startswith(alias) for alias in aliases):
            content = []
            for follow in lines[index + 1:]:
                if follow.startswith("#"):
                    break
                if follow.strip():
                    content.append(clean_text(follow))
                if len(" ".join(content)) > 1400:
                    break
            value = "\n".join(item for item in content if item)
            if value:
                return value, f"heading:{index + 1}"
    return None, None


def _value(analysis: dict, key: str) -> str:
    return analysis["fields"][key]["value"]


def _decision(decisions: dict, key: str) -> str:
    value = decisions.get(key)
    return clean_text(str(value)) if value else PLACEHOLDER


def _source_section(value: str, fallback: str) -> str:
    if value == PLACEHOLDER:
        return f"ㅇ {fallback} {PLACEHOLDER}"
    lines = [clean_text(part) for part in re.split(r"\n+|(?=<br)", value) if clean_text(part)]
    return "\n\n".join(f"ㅇ {line}" for line in lines[:12])


def compose_planning(analysis: dict, decisions: dict, evidence: list[dict]) -> str:
    title = _value(analysis, "title")
    objective = _value(analysis, "objective")
    contents = _value(analysis, "contents")
    trends = _value(analysis, "trends")
    need = _value(analysis, "need")
    period = _value(analysis, "period")
    budget = _value(analysis, "budget")
    verified_evidence = [item for item in evidence if item.get("status") == "verified" and item.get("url")]
    references = "\n".join(
        f"- [{item.get('source_id', 'SRC')}] {clean_text(item.get('organization', '출처기관'))}, {clean_text(item.get('title', '자료명'))}, {clean_text(item.get('date', '발표일 미상'))}, {item['url']}"
        for item in verified_evidence
    ) or f"- 외부 사실 근거와 URL {PLACEHOLDER}"
    return f"""# {title} 기술기획보고서

작성일: {date.today().isoformat()}

## Ⅰ. 개요

### 1. 추진배경

{_source_section(need, '수요조사서에서 추진 필요성의 직접 근거를 확인할 수 없습니다.')}

※ 정책·시장·기술 관련 외부 사실은 검증된 출처가 등록된 범위에서만 확정합니다. {PLACEHOLDER}

### 2. 개념 및 범위

ㅇ 본 사업은 입력 수요의 목표인 “{objective}”를 연구개발 사업 관점에서 구체화합니다.

ㅇ 포함·제외 범위: {_decision(decisions, 'scope')}

### 3. 사업 근거

ㅇ 법령·상위계획·국가전략과의 연결 근거 {PLACEHOLDER}

### 4. 주요동향

{_source_section(trends, '정책·산업·시장·기술 동향의 출처 확인이 필요합니다.')}

## Ⅱ. 사업계획

### 1. 사업목표 및 범위

◈ 최종목표: {objective}

| 항목 | 확정 또는 검토 내용 | 출처 상태 |
| --- | --- | --- |
| 기술분류 | {_value(analysis, 'classification')} | 입력 원문 또는 {PLACEHOLDER} |
| 사업기간 | {period} | 입력 원문 또는 {PLACEHOLDER} |
| 정부출연금/예산 | {budget} | 입력 원문 또는 {PLACEHOLDER} |
| 사업구조 | {_decision(decisions, 'structure')} | 담당자 결정 |
| 정책 우선방향 | {_decision(decisions, 'policy_priority')} | 담당자 결정 |

### 2. 주요 내용(연구주제 예시)

{_source_section(contents, '연구주제와 개발내용의 구체화가 필요합니다.')}

※ 세부과제 구성은 연구주제 예시이며 담당자 확인 전 확정하지 않습니다.

## Ⅲ. 사업추진 타당성

### 1. 정부지원 필요성 및 시급성

{_source_section(need, '민간 단독 추진의 한계, 공공성 및 시급성 근거가 필요합니다.')}

### 2. 기존사업과 차별성

ㅇ 비교 대상 사업, 대상·범위·성과물 차이 및 본 사업의 추가성 {PLACEHOLDER}

## Ⅳ. 사업 추진전략

### 1. 사업 추진절차

ㅇ 기획·선정 → 핵심기술 개발 → 통합·검증 → 확산·사업화의 일반 절차를 적용하되, 단계별 기간과 책임주체는 {PLACEHOLDER}

### 2. 연차별 투자계획

| 구분 | 기간 | 정부출연금 | 주요 산출물 |
| --- | --- | --- | --- |
| 전체 | {period} | {budget} | 입력 수요의 목표 달성 결과 |
| 연차별 배분 | {PLACEHOLDER} | {PLACEHOLDER} | {PLACEHOLDER} |

### 3. 성과관리계획

| 지표 | 정의 | 목표값 | 측정방법 | 검증증적 |
| --- | --- | --- | --- | --- |
| 핵심 기능 달성도 | 필수 기능의 구현·검증 수준 | {PLACEHOLDER} | 시험계획에 따른 검증 | 시험성적서·로그 {PLACEHOLDER} |
| 실증 성과 | 합의한 환경에서의 적용 가능성 | {PLACEHOLDER} | 기준선 대비 실증 | 실증보고서 {PLACEHOLDER} |

※ 정량 KPI·대표 실증대상·시험환경·목표 TRL: {_decision(decisions, 'demonstration_trl')} / {_decision(decisions, 'kpi')}

## Ⅴ. 기대효과

{_source_section(need, '기술·산업·사회·정책 효과의 구체화가 필요합니다.')}

## 부록 A. 출처 및 근거 레지스트리

{references}

## 부록 B. 미확정 사항

- 정책 최우선 방향: {_decision(decisions, 'policy_priority')}
- 포함·제외 범위: {_decision(decisions, 'scope')}
- 사업/세부과제 구조: {_decision(decisions, 'structure')}
- 기간·예산·연차배분 검토: {_decision(decisions, 'period_budget')}
- 정량 KPI 및 검증증적: {_decision(decisions, 'kpi')}
- 실증대상·시험환경·TRL: {_decision(decisions, 'demonstration_trl')}
"""


def compose_rfp(planning_markdown: str, analysis: dict, decisions: dict) -> str:
    title = _value(analysis, "title")
    objective = _value(analysis, "objective")
    contents = _value(analysis, "contents")
    need = _value(analysis, "need")
    period = _value(analysis, "period")
    budget = _value(analysis, "budget")
    scope = _decision(decisions, "scope")
    return f"""# {title} 연구개발 RFP(안)

| 관리항목 | 내용 |
| --- | --- |
| 관리번호 | {PLACEHOLDER} |
| 공모유형 | {PLACEHOLDER} |
| 기술분류 | {_value(analysis, 'classification')} |
| 중점분야·기획유형 | {PLACEHOLDER} |
| 품목(문제)명 | {title} |

## 1. 품목(문제) 정의

### 개념

ㅇ 입력 수요의 최종목표인 “{objective}”를 달성하기 위한 연구개발 품목입니다.

### 현재 한계와 핵심 난제

{_source_section(need, '현재 한계와 해결해야 할 핵심 난제의 직접 근거가 필요합니다.')}

### 최종목표와 범위

ㅇ 최종목표: {objective}

ㅇ 포함·제외 범위: {scope}

ㅇ 구현 방식은 제안자가 제시하되, 필수 결과와 검증조건을 충족해야 합니다.

| As-is | To-be |
| --- | --- |
| 현행 수준·기준선 {PLACEHOLDER} | 검증 가능한 목표 상태 {PLACEHOLDER} |

### 필수 요구사항

| 유형 | 필수 결과 | 검증조건·증적 |
| --- | --- | --- |
| 기능 | 제안 범위의 핵심 기능 구현 | 기능 시험결과·소스/설계 산출물 |
| 실증 | 합의된 실제 환경 또는 재현 가능한 테스트베드 검증 | 실증계획·결과보고서·로그 |
| 상호운용성 | 적용 대상 간 인터페이스와 연계조건 제시 | 연동 시험결과 {PLACEHOLDER} |
| 보안·성능 | 기준선, 목표값, 시험조건, 실패·복구 기준 제시 | 공인 또는 합의된 시험증적 {PLACEHOLDER} |
| 산출물 | 참조모델·시험방법·운영지침·증적 제출 | 산출물 목록과 인수기준 |

### 개발내용 예시

{_source_section(contents, '개발내용은 제안자가 목표 달성에 적합하게 제시해야 합니다.')}

※ 위 개발내용은 예시이며 필수 결과를 훼손하지 않는 범위에서 제안자의 창의적 해법을 허용합니다.

## 2. 현황 및 필요성

{_source_section(need, '기술·시장·정책 현황과 미충족 수요의 출처 보강이 필요합니다.')}

## 3. 수요분석

ㅇ 수요기관·사용자·적용환경·도입장벽·확산경로 {PLACEHOLDER}

## 4. 기대 효과

{_source_section(need, '기술·산업·사회적 기대효과의 구체화가 필요합니다.')}

## 5. 개발기간/예산/추진체계

| 항목 | 내용 |
| --- | --- |
| 개발기간 | {period} |
| 정부지원연구개발비 | {budget} |
| 연차별 기간·예산 | {PLACEHOLDER} |
| 연구유형 | {PLACEHOLDER} |
| 착수/종료 시점·개월 수 | {PLACEHOLDER} |
| 주관·참여기관 조건 | {PLACEHOLDER} |
| 대표 실증환경·수요기관 | {_decision(decisions, 'demonstration_trl')} |
| 목표 TRL | {PLACEHOLDER} |

## 성과지표 및 검증조건

| 지표명 | 정의 | 목표값 | 측정방법 | 검증증적 |
| --- | --- | --- | --- | --- |
| 필수 기능 충족률 | 합의된 필수 기능의 완료 수준 | {_decision(decisions, 'kpi')} | 요구사항 추적 시험 | 시험성적서·추적표 |
| 실증 성공도 | 합의된 환경에서의 적용·운영 수준 | {PLACEHOLDER} | 기준선 대비 실증 | 로그·실증보고서 |

## 미확정 공고조건 및 담당자 질문

- RFP 통합/분리와 공모 단위: {_decision(decisions, 'structure')}
- 범위·제외범위: {scope}
- 관리번호·공모유형·기관 제한: {PLACEHOLDER}
- 기간·전체 예산·품목 배분: {_decision(decisions, 'period_budget')}
- 대표 실증환경·TRL·정량 KPI: {_decision(decisions, 'demonstration_trl')} / {_decision(decisions, 'kpi')}
"""
