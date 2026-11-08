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
    bg(value) {
      if (value?.kind === "linear_gradient") {
        throw new TypeError("bg(value) expects Color, not Background");
      }
      state.calls.push(["bg", value]);
      return proxy;
    },
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
export const Background = {};
export function setGradientEnabled(enabled) {
  if (enabled) {
    Background.linear_gradient = (angle, from, to) =>
      Object.freeze({ kind: "linear_gradient", angle, from, to });
  } else {
    delete Background.linear_gradient;
  }
}
setGradientEnabled(true);
export const PathBuilder = {
  fill() {
    return {
      points: [],
      move_to(x, y) { this.points.push([x, y]); return this; },
      line_to(x, y) { this.points.push([x, y]); return this; },
      close() { this.closed = true; return this; },
      build() { return { kind: "path", points: this.points, closed: this.closed }; },
    };
  },
};
export function paintPath(path, background) {
  return makeElement("paint_path").paint_background(background).paint_geometry(path);
}
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
globalThis.window = {
  paint_path(path, background) { return host.paintPath(path, background); },
};

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
        source_path: "knowledge/tasks/task-abc.md",
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
    paint_path(path, background) { return host.paintPath(path, background); },
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

function backgroundOf(node) {
  return (node.__calls ?? []).find(call => call[0] === "bg")?.[1];
}

function isTranslucentHex(color) {
  return /^#[0-9a-f]{8}$/i.test(color ?? "") && !color.endsWith("00") && !color.endsWith("ff");
}

function findById(root, id) {
  return nodesOf(root).find(node =>
    (node.__calls ?? []).some(call => call[0] === "id" && call[1] === id)
  );
}

function parentOf(root, target) {
  return nodesOf(root).find(node => (node.__children ?? []).includes(target));
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

test("六个阶段列头固定等高，并由阶段行从顶部拉伸对齐", () => {
  const root = newView().render();
  const firstStage = findById(root, "opc-dashboard-stage-proposed");
  const stageRow = parentOf(root, firstStage);
  const boardContent = parentOf(root, stageRow);
  const board = parentOf(root, boardContent);
  const boardAndPreview = parentOf(root, board);
  assert.ok(boardAndPreview, "看板与预览应挂在同一个横向容器中");
  assert.equal(
    hasCall(boardAndPreview, "items_stretch"),
    true,
    "看板外层不应使用 h_flex 默认的垂直居中",
  );

  assert.ok(stageRow, "阶段列应挂在同一个横向容器中");
  assert.equal(hasCall(stageRow, "w_full"), true, "阶段行应铺满可用宽度");
  assert.equal(hasCall(stageRow, "items_stretch"), true, "阶段行不应使用 h_flex 默认的垂直居中");

  for (const key of ["proposed", "drafting", "reviewing", "ready", "published", "reviewed"]) {
    const header = findById(root, `opc-dashboard-stage-header-${key}`);
    assert.ok(header, `缺少阶段列头：${key}`);
    assert.equal(hasCall(header, "h", 58), true, `${key} 列头应固定为 58px`);
    assert.equal(hasCall(header, "flex_none"), true, `${key} 列头不应被卡片内容挤压`);
  }
});

test("阶段列和进度轨道自适应铺满，并保留 220px 最低宽度", () => {
  const root = newView().render();
  const rail = findById(root, "opc-dashboard-progress-rail");
  assert.ok(rail, "缺少阶段进度轨道");
  assert.equal(hasCall(rail, "w_full"), true, "进度轨道应铺满可用宽度");

  for (const key of ["proposed", "drafting", "reviewing", "ready", "published", "reviewed"]) {
    const stage = findById(root, `opc-dashboard-stage-${key}`);
    assert.ok(stage, `缺少阶段列：${key}`);
    assert.equal(hasCall(stage, "flex_1"), true, `${key} 阶段列应等分剩余宽度`);
    assert.equal(hasCall(stage, "min_w", 220), true, `${key} 阶段列应保留最低宽度`);
    assert.equal(hasCall(stage, "w", 260), false, `${key} 阶段列不应继续固定为 260px`);
    assert.equal(hasCall(stage, "flex_none"), false, `${key} 阶段列应允许横向伸展`);

    const railNode = findById(root, `opc-dashboard-rail-${key}`);
    const railSlot = parentOf(root, parentOf(root, railNode));
    assert.ok(railSlot, `缺少阶段轨道槽：${key}`);
    assert.equal(hasCall(railSlot, "flex_1"), true, `${key} 轨道槽应与阶段列同步等分`);
    assert.equal(hasCall(railSlot, "min_w", 220), true, `${key} 轨道槽应与阶段列最低宽度一致`);
  }
});

test("内容项使用低圆角与左侧状态光条的 Signal Card", () => {
  const root = newView().render();
  const card = findById(root, "opc-dashboard-card-content-content-1");
  assert.ok(card, "内容项应有稳定的 Signal Card id");
  assert.equal(hasCall(card, "rounded", 3), true);
  assert.equal(hasCall(card, "border_l", 2), true);
});

test("Aurora 环境层铺满整个 dashboard 根容器", () => {
  const root = newView().render();
  const ambient = findById(root, "opc-dashboard-ambient");
  assert.ok(ambient, "看板应包含 Aurora 环境层");
  assert.equal(parentOf(root, ambient), root, "Aurora 应直接覆盖整个 dashboard，而不是只覆盖阶段区");
  assert.equal(hasCall(root, "relative"), true);
  assert.equal(hasCall(root, "overflow_hidden"), true);
});

test("上层面板和卡片使用分层透明背景，但不降低文字层 opacity", () => {
  const root = newView().render();
  const panelIds = [
    "opc-dashboard-header",
    "opc-dashboard-filters",
    "opc-dashboard-actions",
    "opc-dashboard-stage-drafting",
  ];
  for (const id of panelIds) {
    const panel = findById(root, id);
    assert.ok(panel, `缺少上层面板：${id}`);
    assert.equal(isTranslucentHex(backgroundOf(panel)), true, `${id} 应使用带 alpha 的背景色`);
    assert.equal((panel.__calls ?? []).some(call => call[0] === "opacity"), false, `${id} 不应让文字一起变淡`);
  }

  const stage = findById(root, "opc-dashboard-stage-drafting");
  const signalCard = findById(root, "opc-dashboard-card-content-content-1");
  const actionCard = findById(root, "opc-dashboard-action-task-task-abc");
  for (const card of [signalCard, actionCard]) {
    assert.ok(card, "缺少上层业务卡片");
    assert.equal(isTranslucentHex(backgroundOf(card)), true, "业务卡片应使用带 alpha 的背景色");
    assert.equal((card.__calls ?? []).some(call => call[0] === "opacity"), false, "卡片文字应保持不透明");
    assert.ok(
      Number.parseInt(backgroundOf(card).slice(-2), 16) < Number.parseInt(backgroundOf(stage).slice(-2), 16),
      "业务卡片应比阶段面板更透明，让 Aurora 能透出",
    );
  }
});

test("右侧 Editor 面板保持不透明背景", async () => {
  const view = newView();
  await view.openSource("knowledge/content/content-1/主稿.md");
  const preview = findById(view.render(), "opc-dashboard-preview");
  assert.ok(preview, "选中文件后应显示右侧 Editor 面板");
  assert.equal(backgroundOf(preview), "#000000");
  assert.equal(isTranslucentHex(backgroundOf(preview)), false);
});

test("Aurora 兼容没有 Background.opacity 的 Herdr runtime，并固定显示六个阶段节点", () => {
  const root = newView().render();
  const ambient = findById(root, "opc-dashboard-ambient");
  assert.ok(ambient, "看板区域应有 Aurora 环境光层");
  assert.equal(
    (ambient.__calls ?? []).some(call =>
      call[0] === "paint_background" && call[1]?.kind === "linear_gradient"
    ),
    true,
  );
  for (const key of ["proposed", "drafting", "reviewing", "ready", "published", "reviewed"]) {
    assert.ok(findById(root, `opc-dashboard-rail-${key}`), `缺少阶段轨道节点：${key}`);
  }
});

test("旧 Herdr 缺少 native gradient 时降级为主题色光层", () => {
  host.setGradientEnabled(false);
  try {
    const root = newView().render();
    const ambient = findById(root, "opc-dashboard-ambient");
    assert.ok(ambient, "降级后仍应保留环境光层");
    assert.equal(hasCall(ambient, "bg", "#000000"), true);
  } finally {
    host.setGradientEnabled(true);
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
