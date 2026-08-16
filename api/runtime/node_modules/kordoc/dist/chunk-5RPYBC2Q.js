#!/usr/bin/env node

// src/hwpx/gongmun-surface.ts
var BODY_FONTS = ["myeongjo", "gothic"];
var H2_MARKERS = ["box", "number", "none"];
var BULLET2_CHARS = ["\u3147", "\u25CB"];
var FONT_ROLE_KEYS = ["body", "heading", "ref", "table"];
var SIZE_KEYS = [
  "dae",
  "cham",
  "chapter",
  "coverTitle",
  "coverSub",
  "tocLabel",
  "tocRoman",
  "tocItem",
  "table",
  "bodyTitle"
];
var DOC_HEAD_KEYS = ["org", "to", "via", "title"];
var DOC_FOOT_KEYS = [
  "sender",
  "drafter",
  "reviewer",
  "approver",
  "cooperator",
  "docNum",
  "receive",
  "address",
  "site",
  "phone",
  "fax",
  "email",
  "disclosure"
];
var NOTICE_HEAD_KEYS = ["no", "date", "sender"];
var PRESS_CONTACT_KEYS = ["dept", "manager", "phone"];
var BODY_PT_RANGE = { min: 6, max: 40 };
var LINE_SPACING_RANGE = { min: 50, max: 300 };
var SIZE_PT_RANGE = { min: 6, max: 60 };
var APPROVAL_MAX = 6;
function buildGongmunOptions(input) {
  const g = { preset: input.preset };
  if (input.font) g.bodyFont = input.font;
  if (input.bodyPt !== void 0) g.bodyPt = input.bodyPt;
  if (input.lineSpacing !== void 0) g.lineSpacing = input.lineSpacing;
  if (input.cover === false) {
    g.cover = false;
  } else if (input.org || input.date) {
    g.cover = { ...input.org ? { org: input.org } : {}, ...input.date ? { date: input.date } : {} };
  } else if (input.cover === true) {
    g.cover = true;
  }
  if (input.toc !== void 0) g.toc = input.toc;
  if (input.approval && input.approval.length > 0) g.approval = input.approval;
  if (input.pageNumbers !== void 0) g.pageNumbers = input.pageNumbers;
  if (input.endMark !== void 0) g.endMark = input.endMark;
  if (input.bodyTitleBox !== void 0) g.bodyTitleBox = input.bodyTitleBox;
  if (input.h2Marker) g.h2Marker = input.h2Marker;
  if (input.fonts) g.fonts = input.fonts;
  if (input.sizes) g.sizes = input.sizes;
  if (input.bullet2) g.bullet2 = input.bullet2;
  if (input.suppressSingle !== void 0) g.suppressSingle = input.suppressSingle;
  if (input.docHead) g.docHead = input.docHead;
  if (input.docFoot) g.docFoot = input.docFoot;
  if (input.reportInfo) g.reportInfo = input.reportInfo;
  if (input.noticeHead) g.noticeHead = input.noticeHead;
  if (input.press) g.press = input.press;
  return g;
}

export {
  BODY_FONTS,
  H2_MARKERS,
  BULLET2_CHARS,
  FONT_ROLE_KEYS,
  SIZE_KEYS,
  DOC_HEAD_KEYS,
  DOC_FOOT_KEYS,
  NOTICE_HEAD_KEYS,
  PRESS_CONTACT_KEYS,
  BODY_PT_RANGE,
  LINE_SPACING_RANGE,
  SIZE_PT_RANGE,
  APPROVAL_MAX,
  buildGongmunOptions
};
//# sourceMappingURL=chunk-5RPYBC2Q.js.map