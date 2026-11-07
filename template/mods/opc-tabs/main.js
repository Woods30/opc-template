// OPC 标签栏：基于 Herdr 自带的 tabs mod 复制一份，只多一个「看板」入口。
//
// 为什么要复制：Files / Changes 那个按钮组是自带 tabs mod 里写死的
// （shared("workspace.panels") 只过滤这两个），想在右上角跟它们平级加一个
// 入口，只能按 Herdr 文档说的做法复制一份再改（mod.clone before editing）。
// 自带 mod 升级后若换了行为，这份要跟着对一次——差异都标了「OPC 改动」。
//
// 看板入口做三件事：
//   1. 没有看板 tab → 开一个（tab.new，mod + props）；
//   2. 看板 tab 在前台 → 关掉；
//   3. 看板 tab 在后台 → 切过去。
import { View, div, svg, image } from "gpui-kit";
import { h_flex } from "gpui-base";
import {
  spaces,
  panes,
  run,
  openOverlay,
  theme,
  window,
  shared,
  layout,
  settings,
  props,
  nextCommand,
  readTextFile,
} from "herdr";
import {
  DASHBOARD_MOD,
  instanceProbePath,
  isOpcInstance,
  dashboardTabId,
  isDashboardTabActive,
  dashboardTogglePlan,
} from "./model.js";

function find(node, id) {
  if (node?.id === id) return node;
  for (const child of node?.children ?? []) {
    const found = find(child, id);
    if (found) return found;
  }
  return null;
}

export default class Tabs extends View {
  init(_props, cx) {
    this.pressed = null;
    this.panels = JSON.parse(localStorage.getItem("panels") ?? "{}");
    // 全局只装一份：实例目录从当前 space 的 folder 推断。
    // 探测是异步的，所以先隐藏入口，读到实例标记后再显示。
    this.cx = cx;
    this.dashboardMod = DASHBOARD_MOD;
    this.instance = "";
    this.probeFolder = "";
    this.probeState = "unknown";
    this.probeInFlight = false;
    this.refreshInstance(cx);
    cx.timer.every(2000, cx => this.refreshInstance(cx));
    // 快捷键：keys.json 里 opc-tabs.dashboard 交到这里。
    cx.spawn(async cx => {
      for (;;) {
        const command = await nextCommand();
        if (command === "dashboard") this.toggleDashboard();
        cx.notify();
      }
    });
  }

  // 当前 space 是 OPC 实例才显示入口；切 space 时同步重置，绝不复用上一个实例。
  refreshInstance(cx) {
    const space = spaces().find(p => p.active);
    const folder = space?.folder ?? "";
    if (space?.machine) {
      this.probeFolder = folder;
      this.probeState = "not-opc";
      this.instance = "";
      return;
    }
    if (folder !== this.probeFolder) {
      this.probeFolder = folder;
      this.probeState = "unknown";
      this.instance = "";
      this.probe(folder, cx);
      return;
    }
    if (this.probeState === "unknown") this.probe(folder, cx);
  }

  probe(folder, cx) {
    if (!folder || this.probeInFlight) return;
    this.probeInFlight = true;
    cx.spawn(async () => {
      let text = null;
      try {
        text = await readTextFile(instanceProbePath(folder));
      } catch {
        text = null;
      }
      this.probeInFlight = false;
      if (this.probeFolder !== folder) return;
      this.probeState = isOpcInstance(text) ? "opc" : "not-opc";
      this.instance = this.probeState === "opc" ? folder : "";
      cx.notify();
    });
  }

  // The side panel is remembered per space: switching shows that space's choice
  // (closed if it never had one), and opening or closing it records it.
  syncPanel(space, panel, body, enabled) {
    if (!space || !panel) return;
    const now = panel.hidden ? null : body?.active ?? null;
    if (space.id !== this.space) {
      this.refreshInstance(this.cx);
      const first = this.space === undefined;
      this.space = space.id; this.pending = null;
      if (!(first && !(space.id in this.panels))) {
        const stored = this.panels[space.id] ?? null, want = enabled.includes(stored) ? stored : null;
        if (want !== now) {
          this.pending = { want, until: Date.now() + 1000 };
          if (want) { run("layout.select", { stack: "panel-body", child: want }); run("layout.show", { id: "panel" }); }
          else run("layout.hide", { id: "panel" });
          return;
        }
      }
    }
    // Until the restore lands (or something else won), the old state isn't a choice.
    if (this.pending) {
      if (this.pending.want !== now && Date.now() < this.pending.until) return;
      this.pending = null;
    }
    if (this.panels[space.id] === now) return;
    this.panels[space.id] = now;
    localStorage.setItem("panels", JSON.stringify(this.panels));
  }

  // OPC 改动：看板 tab 的开关动作在 model.js 里算，这里只发命令。
  toggleDashboard() {
    if (!this.dashboardMod || !this.instance) return;
    const space = spaces().find(p => p.active);
    const plan = dashboardTogglePlan({
      mod: this.dashboardMod,
      instance: this.instance,
      space: space?.id ?? "",
      tabs: space?.tabs ?? [],
      paneList: panes(),
    });
    for (const step of plan) run(step.command, step.args);
  }

  render() {
    const t = theme();
    const space = spaces().find(p => p.active);
    const shown = space?.tabs ?? [];
    const stop = (_e, cx) => cx.stop_propagation();
    const button = (id, label, action) => div().id(id).size(26).flex_none().flex().items_center().justify_center().rounded(6).text_color(t.dim).hover(s => s.bg(t.hover).text_color(t.foreground))
      .on_mouse_down("left", stop).on_click(action).child(label);
    const item = (c, i) => {
      const program = panes().find(p => p.tab === c.id && p.program?.agent)?.program ?? panes().find(p => p.tab === c.id)?.program;
      const name = /^tb\d+$/.test(c.name) ? program?.name ?? "Terminal" : c.name;
      return h_flex().id(`tab-${c.id}`).h(29).px(10).gap(7).rounded(7).items_center().flex_none().text_size(12.8)
        .border(1).border_color(c.active ? t.border : t.chrome).bg(c.active ? t.raised : t.chrome).text_color(c.active ? t.foreground : t.muted)
        .hover(s => s.bg(t.hover))
        .on_mouse_down("left", (e, cx) => { cx.stop_propagation(); this.pressed = i; if (e.click_count === 2) run("tab.rename", { id: c.id }); })
        .on_mouse_up("left", () => {
          const from = this.pressed; this.pressed = null;
          if (from !== null && from !== i) run("tab.move", { id: shown[from].id, index: space.tabs.findIndex(x => x.id === c.id) + 1 });
          else run("tab.select", { id: c.id });
        })
        .on_mouse_down("right", (_e, cx) => { cx.stop_propagation(); openOverlay({ mod: "menu", kind: "popup", width: 200, props: { tab: "tab", target: { id: c.id, space: space.id } } }); })
        .when(Boolean(program?.icon), el => el.child(program.tint ? svg(program.icon).size(14).text_color(t.muted) : image(program.icon).size(14)))
        .child(div().max_w(170).truncate().child(c.zoomed ? `${name} Z` : name))
        .when(c.status === "working", el => el.child(svg("mods/workspace-chrome/spinner.svg").size(12).flex_none().text_color(t.working).spin(900)))
        .when(c.status === "blocked" || c.status === "done", el => el.child(div().size(6).rounded(3).bg(t[c.status])))
        .when(c.active, el => el.child(div().id(`close-${c.id}`).text_color(t.dim).on_mouse_down("left", stop).on_click((_e, cx) => { cx.stop_propagation(); run("tab.close", { id: c.id }); }).child(svg("mods/pane/close.svg").size(12))));
    };
    const root = layout(), sidebar = find(root, "sidebar"), w = window();
    // Old saved rails and a dragged-narrow sidebar can be smaller than the window buttons.
    const lightsPadding = w?.platform === "macos" && w.titlebar === "none" && !w.fullscreen && root?.traffic_lights
      ? Math.max(10, (root.traffic_lights[0] + 64) / settings().zoom - (sidebar?.hidden ? 0 : sidebar?.size?.px ?? 0))
      : 10;
    const panel = find(root, "panel"), body = find(root, "panel-body");
    const enabled = shared("workspace.panels") ?? ["files", "changes"];
    this.syncPanel(space, panel, body, enabled);
    const panelButton = (id, label, icon) => {
      const on = panel && !panel.hidden && body?.active === id;
      return h_flex().id(`panel-${id}`).h(26).px(8).gap(5).flex_none().items_center().rounded(6)
        .text_size(12).bg(on ? t.selected : t.chrome).text_color(on ? t.foreground : t.muted)
        .hover(s => s.bg(t.hover)).on_mouse_down("left", stop)
        .on_click(() => {
          if (on) run("layout.hide", { id: "panel" });
          else { run("layout.select", { stack: "panel-body", child: id }); run("layout.show", { id: "panel" }); }
        }).child(svg(icon).size(14)).child(label);
    };
    // OPC 改动：看板入口，跟 Files / Changes 平级，点一下开关看板 tab。
    // 只有当前 space 是 OPC 实例才出现；非实例目录、远端 space 一律隐藏。
    const folder = space?.folder ?? "";
    const showDashboard = Boolean(this.dashboardMod && this.instance)
      && this.instance === folder && !space?.machine;
    const dashboardButton = () => {
      if (!showDashboard) return null;
      const on = isDashboardTabActive(this.dashboardMod, shown, panes());
      return h_flex().id("panel-opc-dashboard").h(26).px(8).gap(5).flex_none().items_center().rounded(6)
        .text_size(12).bg(on ? t.selected : t.chrome).text_color(on ? t.foreground : t.muted)
        .hover(s => s.bg(t.hover)).on_mouse_down("left", stop)
        .on_click(() => this.toggleDashboard())
        .child(svg(`mods/${this.dashboardMod}/icon.svg`).size(14)).child("看板");
    };
    return h_flex().size_full().min_w(0).px(10).pl(lightsPadding).gap(3).items_center().bg(t.chrome).border_b(1).border_color(t.border)
      .on_mouse_up("left", () => { this.pressed = null; })
      .on_scroll_wheel(e => { if (Math.abs(e.delta.y) >= 1) run(e.delta.y > 0 ? "tab.prev" : "tab.next"); })
      .child(h_flex().id("tab-scroll").flex_1().min_w(0).h_full().items_center().gap(3).overflow_x_scrollbar().children(shown.map(item)))
      .child(button("tab-new", "+", () => openOverlay({ mod: "new-menu", kind: "popup", width: 250, height: 512 })))
      .when(enabled.includes("files"), el => el.child(panelButton("files", "Files", "mods/files/file.svg")))
      .when(enabled.includes("changes"), el => el.child(panelButton("changes", "Changes", "mods/changes/changes.svg")))
      .when(showDashboard, el => el.child(dashboardButton()))
      .when(w?.buttons, el => el.child(button("minimize", w.platform === "windows" ? svg("mods/tabs/win-min.svg").size(16) : "−", () => run("window.minimize")))
        .child(button("maximize", w.platform === "windows" ? svg(`mods/tabs/${w.maximized ? "win-restore" : "win-max"}.svg`).size(16) : "□", () => run("window.maximize")))
        .child(button("close-window", w.platform === "windows" ? svg("mods/tabs/win-close.svg").size(16) : svg("mods/pane/close.svg").size(13), () => run("window.close"))));
  }
}
