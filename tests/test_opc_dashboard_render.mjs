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

let taskDepth = 0;
let queuedReads = [];
export async function runTask(task, cx) {
  taskDepth += 1;
  try { return await task(cx); }
  finally { taskDepth -= 1; }
}
export function queueRead(promise) { queuedReads.push(promise); }

function makeElement(kind) {
  const state = { kind: kind, children: [], calls: [] };
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
      if (prop === "__calls") return state.calls;
      if (prop === "__kind") return state.kind;
      if (prop in t) return t[prop];
      // 记录样式与 id 调用，让结构测试能验证 gpui 元素的真实布局契约。
      return (...args) => {
        state.calls.push([prop, ...args]);
        return proxy;
      };
    },
  });
  return proxy;
}

export function div() { return makeElement("div"); }
export function h_flex() { return makeElement("h_flex"); }
export function v_flex() { return makeElement("v_flex"); }
export const Background = {
  linear_gradient(angle, from, to) {
    return {
      kind: "linear_gradient",
      angle,
      from,
      to,
      opacity(factor) { return { ...this, opacity: factor }; },
    };
  },
};
export const TextView = {
  markdown(id, text) { return makeElement("text"); },
};
export const EditorState = {
  new(options) {
    if (taskDepth === 0) throw new Error("EditorState.new requires task context");
    return {
      options,
      released: false,
      release() { this.released = true; },
    };
  },
};
export const Editor = {
  new(state) { return makeElement("editor").child(\`CODE:\${state.options.value}\`); },
};

export function theme() {
  return new Proxy({}, { get: () => "#000000" });
}
export function props() { return {}; }
export function spaces() { return []; }
export function terminals() { return []; }
export function settings() { return { font_family: "JetBrains Mono" }; }
export function run() {}
export function exec() { return { code: 0, stdout: "/instance/source.md", stderr: "" }; }
export function readTextFile() {
  return queuedReads.length
    ? queuedReads.shift()
    : Promise.resolve('---\\n{"title":"第一条选题"}\\n---\\n\\n# 第一条选题');
}
export function watchFolder() { return Promise.resolve([]); }
`;

const stubUrl = dataUrl(STUB_SOURCE);
const host = await import(stubUrl);

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
  view.previewEditor = null;
  view.previewRequest = 0;
  view.motionEnabled = true;
  view.pending = null;
  view.pendingAt = 0;
  view.building = false;
  view.cx = {
    notify() {},
    spawn(task) { return host.runTask(task, this); },
  };
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

function nodesOf(node) {
  if (!node || typeof node !== "object") return [];
  const out = [node];
  for (const child of node.__children ?? []) out.push(...nodesOf(child));
  return out;
}

function hasCall(node, method, ...args) {
  return (node.__calls ?? []).some(call =>
    call[0] === method && JSON.stringify(call.slice(1)) === JSON.stringify(args)
  );
}

function findById(root, id) {
  return nodesOf(root).find(node =>
    (node.__calls ?? []).some(call => call[0] === "id" && call[1] === id)
  );
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}

test("一切正常时看板能渲染：告警条与预览面板都不该出现", () => {
  const view = newView();
  // 没有告警、没有陈旧缓存、也没选中源文件：banner() 与 previewPanel() 都会没有内容。
  assert.doesNotThrow(() => view.render(), "渲染不应把 null 交给 child()");
  const texts = textsOf(view.render());
  assert.equal(texts.includes("校验报错 1 条：看板用的是上一版缓存"), false);
  assert.equal(texts.includes("文件内容"), false);
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

test("选中源文件后在右侧用只读代码视图显示真实内容", async () => {
  const view = newView();
  await view.openSource("knowledge/content/content-1/内容卡.md");
  const texts = textsOf(view.render());
  assert.equal(texts.includes("文件内容"), true);
  assert.equal(texts.includes("knowledge/content/content-1/内容卡.md"), true);
  assert.equal(
    texts.includes('CODE:---\n{"title":"第一条选题"}\n---\n\n# 第一条选题'),
    true,
    "应由 Editor 展示包含 frontmatter 的原文，而不是交给 Markdown 渲染",
  );
  assert.equal(view.previewEditor.options.readonly, true);
  assert.equal(view.previewEditor.options.language, "markdown");
});

test("快速切换文件时，较晚完成的旧读取不能覆盖新文件", async () => {
  const view = newView();
  const first = deferred();
  const second = deferred();
  host.queueRead(first.promise);
  host.queueRead(second.promise);

  const openingFirst = view.openSource("knowledge/content/content-1/内容卡.md");
  const openingSecond = view.openSource("knowledge/content/content-1/主稿.md");
  second.resolve("# 新文件");
  await openingSecond;
  first.resolve("# 旧文件");
  await openingFirst;

  assert.equal(view.preview.path, "knowledge/content/content-1/主稿.md");
  assert.equal(view.previewEditor.options.value, "# 新文件");
});

test("切换文件会释放旧 EditorState", async () => {
  const view = newView();
  host.queueRead(Promise.resolve("# 第一个文件"));
  await view.openSource("knowledge/content/content-1/内容卡.md");
  const firstEditor = view.previewEditor;

  host.queueRead(Promise.resolve("# 第二个文件"));
  await view.openSource("knowledge/content/content-1/主稿.md");
  assert.equal(firstEditor.released, true);
  assert.equal(view.previewEditor.options.value, "# 第二个文件");
});

test("读取中关闭预览后，迟到的结果不能重新打开面板", async () => {
  const view = newView();
  const pending = deferred();
  host.queueRead(pending.promise);
  const opening = view.openSource("knowledge/content/content-1/主稿.md");
  view.closePreview();
  pending.resolve("# 迟到的文件");
  await opening;

  assert.equal(view.preview, null);
  assert.equal(view.previewEditor, null);
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
  assert.equal(texts.includes("当前该做什么"), true);
  for (const label of ["选题", "撰写", "审核", "就绪", "已发布", "已复盘"]) {
    assert.equal(texts.includes(label), true, `缺少阶段：${label}`);
  }
  assert.equal(texts.includes("内容卡"), true);
  assert.equal(texts.includes("主稿"), true);
});

test("六个阶段列头固定等高，让列内容从同一水平线开始", () => {
  const root = newView().render();
  for (const key of ["proposed", "drafting", "reviewing", "ready", "published", "reviewed"]) {
    const header = findById(root, `opc-dashboard-stage-header-${key}`);
    assert.ok(header, `缺少阶段列头：${key}`);
    assert.equal(hasCall(header, "h", 58), true, `${key} 列头应固定为 58px`);
    assert.equal(hasCall(header, "flex_none"), true, `${key} 列头不应被卡片内容挤压`);
  }
});

test("内容项使用低圆角与左侧状态光条的 Signal Card", () => {
  const root = newView().render();
  const card = findById(root, "opc-dashboard-card-content-content-1");
  assert.ok(card, "内容项应有稳定的 Signal Card id");
  assert.equal(hasCall(card, "rounded", 3), true);
  assert.equal(hasCall(card, "border_l", 2), true);
});

test("阶段轨道固定显示六个节点并使用 Aurora gradient", () => {
  const root = newView().render();
  const ambient = findById(root, "opc-dashboard-ambient");
  assert.ok(ambient, "看板区域应有 Aurora 环境光层");
  assert.equal(
    (ambient.__calls ?? []).some(call => call[0] === "bg" && call[1]?.kind === "linear_gradient"),
    true,
  );
  for (const key of ["proposed", "drafting", "reviewing", "ready", "published", "reviewed"]) {
    assert.ok(findById(root, `opc-dashboard-rail-${key}`), `缺少阶段轨道节点：${key}`);
  }
});

test("有记录的阶段节点与列边框使用原生 pulse", () => {
  const root = newView().render();
  const node = findById(root, "opc-dashboard-rail-drafting");
  const glow = findById(root, "opc-dashboard-stage-glow-drafting");
  assert.ok(node, "撰写阶段节点应存在");
  assert.ok(glow, "有记录的撰写列应存在独立光效层");
  assert.equal(hasCall(node, "loop", "opacity", { from: 0.45, to: 1, period: 1600, easing: "ease-in-out" }), true);
  assert.equal(hasCall(glow, "loop", "opacity", { from: 0.18, to: 0.62, period: 2200, easing: "ease-in-out" }), true);
});

test("关闭动效后保留控制台结构但不挂载任何 loop", () => {
  const view = newView();
  view.toggleMotion();
  const root = view.render();
  assert.equal(textsOf(root).includes("动效 关"), true);
  assert.equal(nodesOf(root).some(node => (node.__calls ?? []).some(call => call[0] === "loop")), false);
  assert.ok(findById(root, "opc-dashboard-ambient"), "关闭动效不应移除 Aurora 背景结构");
});
