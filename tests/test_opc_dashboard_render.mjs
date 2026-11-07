// 看板 mod 的渲染路径测试：node --test tests/test_opc_dashboard_render.mjs
//
// 为什么要单独测 main.js：看板崩过一次（child() 收到 null），而 model.js 的
// 纯逻辑测试完全测不到这条路径——判定逻辑在 model.js，组装元素树在 main.js。
//
// 怎么测：main.js 依赖 gpui-kit / gpui-base / herdr，这三个都不是 npm 包。
// 这里用桩替掉它们：桩按 gpui 的真实契约实现 child()/children()/when()，
// child() 收到 null 就抛 gpui 那条错，于是「渲染时混进 null」在测试里就会炸。
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const modDir = path.join(here, "..", "template", "mods", "opc-dashboard");

function dataUrl(source) {
  return `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`;
}

// gpui 桩：链式样式方法一律返回自己；有语义的是 child/children/when。
// child() 的判定照抄 gpui 的契约：null / undefined 不是合法子节点。
const STUB_SOURCE = `
export class View {}

function makeElement(kind) {
  const state = { kind: kind, children: [] };
  const target = {
    child(value) {
      if (value === null || value === undefined) {
        throw new Error(
          "child(value) expects an element, a string, or an entity from cx.new(Class, props)"
        );
      }
      state.children.push(value);
      return proxy;
    },
    children(list) {
      for (const value of list) this.child(value);
      return proxy;
    },
    when(condition, branch) {
      if (!condition) return proxy;
      const out = branch(proxy);
      return out === undefined ? proxy : out;
    },
  };
  const proxy = new Proxy(target, {
    get(t, prop) {
      if (prop === "__children") return state.children;
      if (prop in t) return t[prop];
      // 其余都是样式方法（gap/px/bg/...）：调用即可，不改变结构。
      return () => proxy;
    },
  });
  return proxy;
}

export function div() { return makeElement("div"); }
export function h_flex() { return makeElement("h_flex"); }
export function v_flex() { return makeElement("v_flex"); }
export const TextView = {
  markdown(id, text) { return makeElement("text"); },
};

export function theme() {
  return new Proxy({}, { get: () => "#000000" });
}
export function props() { return {}; }
export function spaces() { return []; }
export function terminals() { return []; }
export function run() {}
export function exec() { return { code: 0, stdout: "", stderr: "" }; }
export function readTextFile() { return Promise.resolve(""); }
export function watchFolder() { return Promise.resolve([]); }
`;

const stubUrl = dataUrl(STUB_SOURCE);

const modelSource = await readFile(path.join(modDir, "model.js"), "utf8");
const modelUrl = dataUrl(modelSource);
const model = await import(modelUrl);

const mainSource = await readFile(path.join(modDir, "main.js"), "utf8");
const patchedMain = mainSource
  .replace('"gpui-kit"', JSON.stringify(stubUrl))
  .replace('"gpui-base"', JSON.stringify(stubUrl))
  .replace('"herdr"', JSON.stringify(stubUrl))
  .replace('"./model.js"', JSON.stringify(modelUrl));
const mainModule = await import(dataUrl(patchedMain));
const Dashboard = mainModule.default;

const AS_OF = "2026-11-20T09:07:00+08:00";

function payload(overrides = {}) {
  return {
    contract_version: 1,
    generated: true,
    read_only: true,
    as_of: AS_OF,
    counts: {},
    contents: [
      {
        content_id: "content-1",
        title: "第一条选题",
        status: "drafting",
        role: "content",
        priority: null,
        blocked: false,
        target_date: null,
        created_at: "2026-11-18T09:00:00+08:00",
        approval_status: null,
        publication_ids: [],
        source_path: "knowledge/content/content-1/内容卡.md",
        draft_path: "knowledge/content/content-1/主稿.md",
      },
    ],
    publications: [],
    tasks: [
      {
        task_id: "task-abc",
        role: "content",
        requester: "gm",
        requested_at: "2026-11-19 09:30",
        task: "产出本周选题清单",
        acceptance: "10 个选题",
        state: "open",
        reason: null,
        source_path: "knowledge/inbox/content.md",
      },
    ],
    approvals: [],
    channels: [],
    team: [],
    diagnostics: { errors: [], warnings: [] },
    scope: {
      content_ids: ["content-1"],
      publication_ids: [],
      task_ids: ["task-abc"],
      approval_ids: [],
    },
    ...overrides,
  };
}

function newView(overrides = {}) {
  const view = new Dashboard();
  view.instance = "/instance";
  view.payload = payload();
  view.error = "";
  view.actionError = "";
  view.buildErrors = [];
  view.filters = model.emptyFilters();
  view.changed = [];
  view.preview = null;
  view.pending = null;
  view.pendingAt = 0;
  view.building = false;
  view.cx = { notify() {} };
  Object.assign(view, overrides);
  return view;
}

// 收集渲染树里的文本，用来判断某一块有没有真的挂上去。
function textsOf(node) {
  if (typeof node === "string") return [node];
  if (!node || typeof node !== "object") return [];
  const out = [];
  for (const child of node.__children ?? []) out.push(...textsOf(child));
  return out;
}

test("一切正常时看板能渲染：告警条与预览面板都不该出现", () => {
  const view = newView();
  // 没有告警、没有陈旧缓存、也没选中源文件：banner() 与 previewPanel() 都会没有内容。
  assert.doesNotThrow(() => view.render(), "渲染不应把 null 交给 child()");
  const texts = textsOf(view.render());
  assert.equal(texts.includes("校验报错 1 条：看板用的是上一版缓存"), false);
  assert.equal(texts.includes("源文件"), false);
});

test("有校验报错时告警条照常出现", () => {
  const view = newView({
    payload: payload({
      diagnostics: {
        errors: [{ source: "knowledge/content/content-1/内容卡.md", message: "缺主稿" }],
        warnings: [],
      },
    }),
  });
  const texts = textsOf(view.render());
  assert.equal(texts.includes("校验报错 1 条：看板用的是上一版缓存"), true);
});

test("有校验提醒时告警条照常出现", () => {
  const view = newView({
    payload: payload({
      diagnostics: {
        errors: [],
        warnings: [{ source: "knowledge/content/content-1/内容卡.md", message: "缺指标" }],
      },
    }),
  });
  const texts = textsOf(view.render());
  assert.equal(texts.includes("有 1 条校验提醒"), true);
});

test("选中源文件后预览面板照常出现", () => {
  const view = newView({
    preview: {
      path: "knowledge/content/content-1/内容卡.md",
      text: "# 第一条选题",
      error: "",
    },
  });
  const texts = textsOf(view.render());
  assert.equal(texts.includes("源文件"), true);
  assert.equal(texts.includes("knowledge/content/content-1/内容卡.md"), true);
});

// 实例里的载荷是全的：名册、渠道、发布、审批都有。
// 这一条盯住「每个分支都渲染一遍」——某个分支里的 null 同样会炸掉整个视图。
test("载荷完整时各栏都渲染得出来", () => {
  const view = newView({
    payload: payload({
      contents: [
        {
          content_id: "content-1",
          title: "第一条选题",
          status: "drafting",
          role: "content",
          priority: "high",
          blocked: true,
          block_reason: "缺素材",
          target_date: null,
          created_at: "2026-11-18T09:00:00+08:00",
          approval_status: null,
          publication_ids: ["publication-1"],
          source_path: "knowledge/content/content-1/内容卡.md",
          draft_path: "knowledge/content/content-1/主稿.md",
        },
      ],
      publications: [
        {
          publication_id: "publication-1",
          content_id: "content-1",
          channel: "wechat",
          status: "published",
          role: "gm",
          priority: null,
          blocked: false,
          created_at: "2026-11-19T09:00:00+08:00",
          planned_at: null,
          published_at: "2026-11-20T09:07:00+08:00",
          url: "https://example.com/posts/launch",
          approval_status: "approved",
          metrics: { state: "recorded", summary: "48h：阅读 1234", windows: [] },
          needs_metrics: false,
          needs_review: true,
          review: { status: null, conclusion: null, recorded_at: null },
          source_path: "knowledge/content/content-1/publications/publication-1/发布卡.md",
          draft_path: "knowledge/content/content-1/publications/publication-1/渠道稿.md",
        },
      ],
      approvals: [
        {
          entity: "publication",
          id: "publication-1",
          artifact: "渠道稿.md",
          requested_at: "2026-11-19T10:00:00+08:00",
          requested_by: "content",
          source_path: "knowledge/content/content-1/publications/publication-1/发布卡.md",
        },
      ],
      channels: [
        {
          channel: "wechat",
          name: "公众号",
          publication_count: 1,
          account_metrics: { followers: 5000 },
        },
      ],
      team: [{ role: "gm", terminal: "myopc-gm" }],
    }),
  });
  const texts = textsOf(view.render());
  assert.equal(texts.includes("OPC 看板"), true);
  assert.equal(texts.includes("内容流水线"), true);
  assert.equal(texts.includes("发布节奏（计划 0 / 已发布 1）"), true);
  assert.equal(texts.includes("增长复盘（1）"), true);
  assert.equal(texts.includes("角色终端（辅助）"), true);
  assert.equal(texts.includes("myopc-gm"), true);
});
