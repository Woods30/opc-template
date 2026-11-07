// 看板入口的纯逻辑：找到看板 tab，并给出「开 / 关 / 切过去」的动作。
// 不碰 herdr API，方便用 node --test 直接测。

export const DASHBOARD_MOD = "opc-dashboard";
export const INSTANCE_MARKER = ".opc/instance.json";

// 全局只装一份 mod：实例目录从当前 space 的 folder 推断，不再由布局传参。
export function instanceProbePath(folder) {
  if (typeof folder !== "string" || folder === "") return "";
  return `${folder.replace(/\/+$/, "")}/${INSTANCE_MARKER}`;
}

// 只认 install 写入的实例标记，避免任意 .opc/instance.json 把入口点亮。
export function isOpcInstance(text) {
  if (typeof text !== "string" || text.trim() === "") return false;
  try {
    const data = JSON.parse(text);
    return Boolean(data && typeof data === "object" && data.kind === "opc-instance");
  } catch {
    return false;
  }
}

// 看板 mod 在某个 tab 里当唯一面板：pane.mod 就是那个 mod 名。
export function dashboardTabId(mod, tabs, paneList) {
  if (typeof mod !== "string" || mod === "") return null;
  const tabIds = new Set((tabs ?? []).map(tab => tab?.id));
  for (const pane of paneList ?? []) {
    if (pane?.mod === mod && tabIds.has(pane?.tab)) return pane.tab;
  }
  return null;
}

export function isDashboardTabActive(mod, tabs, paneList) {
  const id = dashboardTabId(mod, tabs, paneList);
  if (!id) return false;
  return Boolean((tabs ?? []).find(tab => tab?.id === id)?.active);
}

// 看板入口的三种动作：
// 没有看板 tab → 开一个；已经在前台 → 关掉；在后台 → 切过去。
export function dashboardTogglePlan({ mod, instance, space, tabs, paneList }) {
  if (typeof mod !== "string" || mod === "") return [];
  if (typeof instance !== "string" || instance === "") return [];
  const existing = dashboardTabId(mod, tabs, paneList);
  if (!existing) {
    const args = { name: "看板", mod, props: { instance } };
    if (space) args.space = space;
    return [{ command: "tab.new", args }];
  }
  const active = Boolean((tabs ?? []).find(tab => tab?.id === existing)?.active);
  if (active) return [{ command: "tab.close", args: { id: existing } }];
  return [{ command: "tab.select", args: { id: existing } }];
}
