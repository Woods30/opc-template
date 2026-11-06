// 标签栏副本的纯逻辑测试：node --test tests/test_opc_tabs_mod.mjs
// model.js 是 ES module，但模版仓没有 package.json，直接 import 文件会被当成
// CommonJS；用 data: URL 导入，测的是同一份源码。
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const source = await readFile(
  path.join(here, "..", "template", "mods", "opc-tabs", "model.js"),
  "utf8",
);
const model = await import(
  `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`
);

const MOD = model.DASHBOARD_MOD;
const INSTANCE = "/instance";

function tabs(activeId) {
  return [
    { id: "tb1", name: "gm", active: activeId === "tb1" },
    { id: "tb2", name: "看板", active: activeId === "tb2" },
  ];
}

test("看板 tab 是那个以看板 mod 当面板的 tab", () => {
  const panes = [
    { pane: "p1", mod: MOD, tab: "tb2" },
    { pane: "p2", terminal: "t43", tab: "tb1" },
  ];
  assert.equal(model.dashboardTabId(MOD, tabs("tb1"), panes), "tb2");
  assert.equal(model.dashboardTabId("别的 mod", tabs("tb1"), panes), null);
  assert.equal(model.dashboardTabId("", tabs("tb1"), panes), null);
  assert.equal(model.dashboardTabId(MOD, tabs("tb1"), []), null);
  // 不在这个 space 里的 tab 不算数
  assert.equal(
    model.dashboardTabId(MOD, [{ id: "tb1" }], [{ pane: "p1", mod: MOD, tab: "tb9" }]),
    null,
  );
});

test("看板 tab 在前台才算前台", () => {
  const panes = [{ pane: "p1", mod: MOD, tab: "tb2" }];
  assert.equal(model.isDashboardTabActive(MOD, tabs("tb2"), panes), true);
  assert.equal(model.isDashboardTabActive(MOD, tabs("tb1"), panes), false);
  assert.equal(model.isDashboardTabActive(MOD, tabs("tb1"), []), false);
});

test("没有看板 tab 就开一个，带实例目录", () => {
  const plan = model.dashboardTogglePlan({
    mod: MOD,
    instance: INSTANCE,
    space: "sp1",
    tabs: [{ id: "tb1", name: "gm", active: true }],
    paneList: [],
  });
  assert.deepEqual(plan, [
    {
      command: "tab.new",
      args: {
        name: "看板",
        mod: MOD,
        props: { instance: INSTANCE },
        space: "sp1",
      },
    },
  ]);
});

test("看板 tab 在后台就切过去，在前台就关掉", () => {
  const panes = [{ pane: "p1", mod: MOD, tab: "tb2" }];
  const background = model.dashboardTogglePlan({
    mod: MOD,
    instance: INSTANCE,
    space: "sp1",
    tabs: tabs("tb1"),
    paneList: panes,
  });
  assert.deepEqual(background, [
    { command: "tab.select", args: { id: "tb2" } },
  ]);

  const foreground = model.dashboardTogglePlan({
    mod: MOD,
    instance: INSTANCE,
    space: "sp1",
    tabs: tabs("tb2"),
    paneList: panes,
  });
  assert.deepEqual(foreground, [
    { command: "tab.close", args: { id: "tb2" } },
  ]);
});

test("缺 mod 名或实例目录时不动手", () => {
  assert.deepEqual(
    model.dashboardTogglePlan({
      mod: "",
      instance: INSTANCE,
      space: "sp1",
      tabs: [],
      paneList: [],
    }),
    [],
  );
  assert.deepEqual(
    model.dashboardTogglePlan({
      mod: MOD,
      instance: "",
      space: "sp1",
      tabs: [],
      paneList: [],
    }),
    [],
  );
});

test("实例探测只认 space 根目录的 .opc/instance.json", () => {
  assert.equal(model.instanceProbePath("/instance"), "/instance/.opc/instance.json");
  assert.equal(model.instanceProbePath("/instance/"), "/instance/.opc/instance.json");
  assert.equal(model.instanceProbePath(""), "");
  assert.equal(model.instanceProbePath(null), "");
});

test("实例标记必须是 opc-instance", () => {
  assert.equal(model.isOpcInstance('{"kind":"opc-instance"}'), true);
  assert.equal(model.isOpcInstance('{"kind":"opc-template"}'), false);
  assert.equal(model.isOpcInstance("{}"), false);
  assert.equal(model.isOpcInstance(""), false);
  assert.equal(model.isOpcInstance("not json"), false);
});
