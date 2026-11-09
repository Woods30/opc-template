// 看板的纯逻辑：只处理 Dashboard JSON 契约，不碰 herdr API。
// 渲染与文件监听在 main.js，判定逻辑在这里，方便用 node --test 直接测。

export const CONTRACT_VERSION = 1;

export const HISTORY_CONTENT_STATUSES = ["closed", "cancelled"];
export const HISTORY_PUBLICATION_STATUSES = ["cancelled"];
export const HISTORY_TASK_STATES = ["done", "cancelled"];

export const TIME_WINDOWS = { "7d": 7, "30d": 30, "90d": 90 };

// 生成视图：build 每次都会重写它们，看到它们变化不该再触发 build。
// 用后缀匹配：频道发布记录在 knowledge/business/<频道>/ 下面，目录名随配置变。
export const GENERATED_SUFFIXES = [
  "knowledge/business/dashboard.json",
  "选题日历.md",
  "发布记录.md",
];

// canonical 事实源：只有它们变了才需要重跑 build。work/ 是过程，decisions/ 是日志。
export const CANONICAL_PREFIXES = [
  "knowledge/content/",
  "knowledge/tasks/",
  "knowledge/business/growth/",
];

// 终端名来自实例名册，不按命名规则猜地址。
export function findTeamTerminal(team, role) {
  if (!Array.isArray(team)) return null;
  const entry = team.find(
    item =>
      item &&
      item.role === role &&
      typeof item.terminal === "string" &&
      item.terminal.trim() !== "",
  );
  return entry ? entry.terminal : null;
}

// 聚焦终端的动作序列：看板是同一布局里的 tab，直接按地址聚焦即可。
export function terminalFocusPlan(address) {
  if (!address) return [];
  return [{ command: "pane.focus", args: { terminal: address } }];
}

// 看板只读这些子树里的 canonical 记录；别的路径一律不读。
export const SOURCE_PREFIXES = [
  "knowledge/content/",
  "knowledge/tasks/",
  "knowledge/business/growth/",
];

// 源文件路径来自生成的契约，仍要先按字面量挡住越界写法。
export function isAllowedSourcePath(relativePath) {
  if (typeof relativePath !== "string" || relativePath === "") return false;
  if (relativePath.startsWith("/")) return false;
  if (relativePath.split("/").includes("..")) return false;
  return SOURCE_PREFIXES.some(prefix => relativePath.startsWith(prefix));
}

// 字面量检查挡不住 symlink：content 树里放一个指向 .opc/ 的链接，
// 前缀仍然合法。定位真实文件时用 realpath 再做一次容器检查，
// 并且要求解析后的目标落在允许的 canonical 子树里。
// mod 的 fs/promises 没有 realpath，用实例本来就需要的 python3 做这一步。
export const REALPATH_SNIPPET = [
  "import os, sys",
  "base = os.path.realpath(sys.argv[1])",
  "target = os.path.realpath(os.path.join(base, sys.argv[2]))",
  "prefixes = [os.path.realpath(os.path.join(base, item)) for item in sys.argv[3:]]",
  "if target != base and not target.startswith(base + os.sep):",
  "    sys.exit('源文件越出实例目录')",
  "if not any(target == root or target.startswith(root + os.sep) for root in prefixes):",
  "    sys.exit('源文件不在允许的 canonical 子树内')",
  "print(target)",
].join("\n");

export function emptyFilters() {
  return {
    time: "",
    channel: "",
    contentStatus: "",
    publicationStatus: "",
    role: "",
    priority: "",
    blocked: "",
    includeHistory: false,
  };
}

export function parseDashboard(text) {
  if (typeof text !== "string" || text.trim() === "") {
    return { ok: false, error: "看板缓存是空的：先运行 tools/opc-workflow build" };
  }
  let payload;
  try {
    payload = JSON.parse(text);
  } catch (error) {
    return { ok: false, error: `看板缓存不是合法 JSON：${error.message}` };
  }
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return { ok: false, error: "看板缓存必须是 JSON object" };
  }
  if (payload.contract_version !== CONTRACT_VERSION) {
    return {
      ok: false,
      error: `看板契约版本不匹配：期望 ${CONTRACT_VERSION}，实际 ${payload.contract_version}`,
    };
  }
  return { ok: true, payload };
}

function list(payload, key) {
  const value = payload?.[key];
  return Array.isArray(value) ? value : [];
}

export function counts(payload) {
  const counted = {};
  for (const key of ["contents", "publications", "tasks", "approvals", "channels"]) {
    counted[key] = list(payload, key).length;
  }
  return counted;
}

export function diagnostics(payload) {
  const value = payload?.diagnostics;
  return {
    errors: Array.isArray(value?.errors) ? value.errors : [],
    warnings: Array.isArray(value?.warnings) ? value.warnings : [],
  };
}

function sorted(values) {
  return [...new Set(values.filter(value => typeof value === "string" && value !== ""))].sort();
}

export function filterOptions(payload) {
  const channels = [];
  const contentStatuses = [];
  const publicationStatuses = [];
  const roles = [];
  const priorities = [];
  for (const content of list(payload, "contents")) {
    contentStatuses.push(content.status);
    roles.push(content.role);
    priorities.push(content.priority);
  }
  for (const publication of list(payload, "publications")) {
    channels.push(publication.channel);
    publicationStatuses.push(publication.status);
    roles.push(publication.role);
    priorities.push(publication.priority);
  }
  for (const task of list(payload, "tasks")) roles.push(task.role);
  for (const approval of list(payload, "approvals")) roles.push(approval.requested_by);
  return {
    channels: sorted(channels),
    contentStatuses: sorted(contentStatuses),
    publicationStatuses: sorted(publicationStatuses),
    roles: sorted(roles),
    priorities: sorted(priorities),
  };
}

function stamp(value) {
  if (typeof value !== "string" || value === "") return null;
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? null : parsed;
}

export function withinPast(value, asOf, days) {
  const moment = stamp(value);
  const base = stamp(asOf);
  if (moment === null) return false;
  if (base === null) return true;
  return moment >= base - days * 86400000 && moment <= base;
}

export function withinFuture(value, asOf, days) {
  const moment = stamp(value);
  const base = stamp(asOf);
  if (moment === null) return false;
  if (base === null) return true;
  return moment >= base && moment <= base + days * 86400000;
}

function matchesTime(entity, filters, asOf) {
  const days = TIME_WINDOWS[filters.time];
  if (!days) return true;
  if (entity.planned_at) return withinFuture(entity.planned_at, asOf, days);
  return withinPast(entity.published_at || entity.created_at, asOf, days);
}

function matchesCommon(entity, filters) {
  if (filters.role && entity.role !== filters.role) return false;
  if (filters.priority && entity.priority !== filters.priority) return false;
  if (filters.blocked === "yes" && !entity.blocked) return false;
  if (filters.blocked === "no" && entity.blocked) return false;
  return true;
}

export function applyFilters(payload, filters) {
  const active = { ...emptyFilters(), ...(filters || {}) };
  const asOf = payload?.as_of ?? null;
  const includeHistory = Boolean(active.includeHistory);

  let publications = list(payload, "publications").filter(publication => {
    if (!includeHistory && HISTORY_PUBLICATION_STATUSES.includes(publication.status)) return false;
    if (active.publicationStatus && publication.status !== active.publicationStatus) return false;
    if (active.channel && publication.channel !== active.channel) return false;
    if (!matchesCommon(publication, active)) return false;
    return matchesTime(publication, active, asOf);
  });

  let contents = list(payload, "contents").filter(content => {
    if (!includeHistory && HISTORY_CONTENT_STATUSES.includes(content.status)) return false;
    if (active.contentStatus && content.status !== active.contentStatus) return false;
    if (!matchesCommon(content, active)) return false;
    return matchesTime(content, active, asOf);
  });

  if (active.channel) {
    const kept = new Set(publications.map(publication => publication.content_id));
    contents = contents.filter(content => kept.has(content.content_id));
  }

  const tasks = list(payload, "tasks").filter(task => {
    if (!includeHistory && HISTORY_TASK_STATES.includes(task.state)) return false;
    if (active.role && task.role !== active.role) return false;
    return true;
  });

  const contentIds = new Set(contents.map(content => content.content_id));
  const publicationIds = new Set(publications.map(publication => publication.publication_id));
  const approvals = list(payload, "approvals").filter(approval => {
    if (approval.entity === "content") return contentIds.has(approval.id);
    if (approval.entity === "publication") return publicationIds.has(approval.id);
    return false;
  });

  return {
    contents,
    publications,
    tasks,
    approvals,
    channels: list(payload, "channels"),
    team: list(payload, "team"),
    counts: {
      contents: contents.length,
      publications: publications.length,
      tasks: tasks.length,
      approvals: approvals.length,
      channels: list(payload, "channels").length,
    },
  };
}

export function isEmpty(view) {
  return (
    view.contents.length === 0 &&
    view.publications.length === 0 &&
    view.tasks.length === 0 &&
    view.approvals.length === 0
  );
}

// 空看板和坏看板是两回事：
// 业务刚起步时没有内容是正常状态，不该用错误色喊人；
// 缓存读不到或 JSON 坏了才是基础设施问题，那才该红。
export function dashboardState(payload, filters) {
  const view = applyFilters(payload, filters ?? emptyFilters());
  const counted = counts(payload);
  const total =
    counted.contents + counted.publications + counted.tasks + counted.approvals;
  if (total === 0) {
    return {
      level: "info",
      title: "看板还没有业务数据",
      detail:
        "这是正常状态：业务刚起步时还没有内容、发布或任务。生成第一条内容后，这里就会有动态。",
      empty: true,
    };
  }
  if (isEmpty(view)) {
    return {
      level: "info",
      title: "当前筛选下没有记录",
      detail:
        "放宽筛选条件就能看到其他记录；勾上「含历史」可以带上已关闭的内容与旧任务。",
      empty: false,
    };
  }
  return null;
}

export function urgentItems(view) {
  const items = [];
  for (const content of view.contents) {
    if (content.blocked) {
      items.push({
        kind: "blocked",
        entity: "content",
        id: content.content_id,
        title: content.title || content.content_id,
        detail: content.block_reason || "内容受阻",
        role: content.role,
        source_path: content.source_path,
      });
    }
  }
  for (const publication of view.publications) {
    if (publication.needs_metrics) {
      items.push({
        kind: "metrics",
        entity: "publication",
        id: publication.publication_id,
        title: publication.publication_id,
        detail: "指标未记录完整",
        role: publication.role,
        source_path: publication.metrics_path || publication.source_path,
      });
    }
    if (publication.needs_review) {
      items.push({
        kind: "review",
        entity: "publication",
        id: publication.publication_id,
        title: publication.publication_id,
        detail: "复盘未完成",
        role: publication.role,
        source_path: publication.source_path,
      });
    }
  }
  for (const approval of view.approvals) {
    items.push({
      kind: "approval",
      entity: approval.entity,
      id: approval.id,
      title: approval.id,
      detail: `待审批：${approval.artifact || ""}`,
      role: approval.requested_by,
      source_path: approval.source_path,
    });
  }
  return items;
}

export const WORKFLOW_STAGES = [
  { key: "proposed", label: "选题", hint: "确定要解决的问题" },
  { key: "drafting", label: "撰写", hint: "形成内容或渠道稿" },
  { key: "reviewing", label: "审核", hint: "校对并等待审批" },
  { key: "ready", label: "就绪", hint: "排期并准备发布" },
  { key: "published", label: "已发布", hint: "补齐指标数据" },
  { key: "reviewed", label: "已复盘", hint: "沉淀结论与动作" },
];

const CONTENT_STAGE = {
  proposed: "proposed",
  drafting: "drafting",
  reviewing: "reviewing",
  ready: "ready",
  closed: "reviewed",
  cancelled: "reviewed",
};

const PUBLICATION_STAGE = {
  adapting: "drafting",
  reviewing: "reviewing",
  scheduled: "ready",
  published: "published",
  reviewed: "reviewed",
  cancelled: "reviewed",
};

function stageItem(kind, entity) {
  const content = kind === "content";
  const id = content ? entity.content_id : entity.publication_id;
  return {
    kind,
    id,
    title: content
      ? entity.title || id
      : [entity.channel, entity.publication_id].filter(Boolean).join(" · "),
    status: entity.status || (content ? "proposed" : "adapting"),
    role: entity.role || "",
    detail: content ? entity.content_id : entity.content_id || "",
    priority: entity.priority || null,
    blocked: Boolean(entity.blocked),
    block_reason: entity.block_reason || "",
    source_path: entity.source_path || null,
    draft_path: entity.draft_path || null,
  };
}

// 阶段始终完整返回，空列也不折叠；这样看板的位置本身就表达流程。
export function workflowStages(view) {
  const stages = WORKFLOW_STAGES.map(stage => ({ ...stage, items: [] }));
  const byKey = new Map(stages.map(stage => [stage.key, stage]));
  for (const content of view.contents || []) {
    const key = CONTENT_STAGE[content.status || "proposed"];
    if (key) byKey.get(key).items.push(stageItem("content", content));
  }
  for (const publication of view.publications || []) {
    const key = PUBLICATION_STAGE[publication.status || "adapting"];
    if (key) byKey.get(key).items.push(stageItem("publication", publication));
  }
  return stages;
}

// 顶部行动条按“需要 owner 决策 → 已阻塞 → 已派工 → 发布后补账”排序。
export function currentActions(view) {
  const actions = [];
  for (const approval of view.approvals || []) {
    actions.push({
      kind: "approval",
      id: approval.id,
      title: `审批 ${approval.artifact || approval.id}`,
      detail: approval.id,
      role: "owner",
      source_path: approval.source_path || null,
    });
  }
  for (const entity of [...(view.contents || []), ...(view.publications || [])]) {
    if (!entity.blocked) continue;
    actions.push({
      kind: "blocked",
      id: entity.content_id || entity.publication_id,
      title: entity.title || entity.publication_id || entity.content_id,
      detail: entity.block_reason || "需要解除阻塞",
      role: entity.role || "",
      source_path: entity.source_path || null,
    });
  }
  for (const task of view.tasks || []) {
    if (task.state !== "open") continue;
    actions.push({
      kind: "task",
      id: task.task_id,
      title: task.task || task.task_id,
      detail: task.acceptance ? `验收：${task.acceptance}` : "",
      role: task.role || "",
      source_path: task.source_path || null,
    });
  }
  for (const publication of view.publications || []) {
    if (publication.needs_metrics) {
      actions.push({
        kind: "metrics",
        id: publication.publication_id,
        title: `补齐 ${publication.publication_id} 的指标`,
        detail: publication.metrics?.summary || "指标未记录完整",
        role: "growth",
        source_path: publication.metrics_path || publication.source_path || null,
      });
    } else if (publication.needs_review) {
      actions.push({
        kind: "review",
        id: publication.publication_id,
        title: `复盘 ${publication.publication_id}`,
        detail: publication.review?.conclusion || "发布后复盘未完成",
        role: "growth",
        source_path: publication.source_path || null,
      });
    }
  }
  return actions;
}

export function pipeline(view) {
  return workflowStages(view)
    .filter(stage => stage.items.some(item => item.kind === "content"))
    .map(stage => ({
      status: stage.key,
      items: stage.items.filter(item => item.kind === "content"),
    }));
}

export function publicationCalendar(view) {
  const scheduled = view.publications
    .filter(publication => publication.planned_at)
    .sort((left, right) => left.planned_at.localeCompare(right.planned_at));
  const published = view.publications
    .filter(publication => publication.published_at)
    .sort((left, right) => right.published_at.localeCompare(left.published_at));
  return { scheduled, published };
}

export function pendingForOwner(view) {
  const tasks = view.tasks
    .filter(task => task.state === "open")
    .map(task => ({
      kind: "task",
      entity: "task",
      id: task.task_id,
      title: task.task,
      detail: task.acceptance ? `验收：${task.acceptance}` : "",
      role: task.role,
      requester: task.requester,
      source_path: task.source_path,
    }));
  const approvals = view.approvals.map(approval => ({
    kind: "approval",
    entity: approval.entity,
    id: approval.id,
    title: approval.id,
    detail: `待审批：${approval.artifact || ""}`,
    role: approval.requested_by,
    requester: approval.requested_by,
    source_path: approval.source_path,
  }));
  return [...approvals, ...tasks];
}

export function channelGrowth(view, filters) {
  const active = filters?.channel || "";
  return view.channels
    .filter(channel => !active || channel.channel === active)
    .map(channel => ({
      channel: channel.channel,
      name: channel.name || channel.channel,
      publication_count: view.publications.filter(
        publication => publication.channel === channel.channel,
      ).length,
      account_metrics: channel.account_metrics || {},
    }));
}

export function reviewItems(view) {
  return view.publications
    .filter(publication => publication.needs_review || publication.review?.conclusion)
    .map(publication => ({
      publication_id: publication.publication_id,
      channel: publication.channel,
      published_at: publication.published_at,
      conclusion: publication.review?.conclusion || "",
      needs_review: Boolean(publication.needs_review),
      metrics: publication.metrics?.summary || "",
      source_path: publication.source_path,
    }));
}

export function isGeneratedPath(path) {
  return GENERATED_SUFFIXES.some(suffix => path.endsWith(suffix));
}

// build 失败时它把诊断打在 stderr 上，格式是「错误：<源>：<原因>」；
// 解析出来才能让 owner 点开那条记录。
export function parseBuildDiagnostics(text) {
  const entries = [];
  for (const line of String(text || "").split("\n")) {
    const match = /^(错误|警告)：(.+?)：(.+)$/.exec(line.trim());
    if (!match) continue;
    entries.push({
      level: match[1] === "错误" ? "error" : "warning",
      source: match[2],
      message: match[3],
    });
  }
  return entries;
}

export function shouldRebuild(changedPaths) {
  for (const path of changedPaths || []) {
    if (isGeneratedPath(path)) continue;
    if (CANONICAL_PREFIXES.some(prefix => path.includes(prefix))) return true;
  }
  return false;
}

// 缓存过期只认真实进契约的源文件：build 自己重写的 generated 视图、
// 过程日志与工作稿变了，都不算看板缓存过期。
export function staleState(changedPaths, dashboardPath) {
  const changed = (changedPaths || []).filter(path => {
    if (path === dashboardPath) return false;
    if (isGeneratedPath(path)) return false;
    return CANONICAL_PREFIXES.some(prefix => path.includes(prefix));
  });
  return { stale: changed.length > 0, changed };
}

export function bannerState(payload, stale) {
  const { errors, warnings } = diagnostics(payload);
  if (errors.length > 0) {
    return {
      level: "error",
      title: `校验报错 ${errors.length} 条：看板用的是上一版缓存`,
      detail: errors.map(error => `${error.source}：${error.message}`).join("；"),
    };
  }
  if (stale?.stale) {
    return {
      level: "warning",
      title: "看板缓存可能已过期",
      detail: `这些源文件刚变过：${(stale.changed || []).join("、")}`,
    };
  }
  if (warnings.length > 0) {
    return {
      level: "warning",
      title: `有 ${warnings.length} 条校验提醒`,
      detail: warnings.map(warning => `${warning.source}：${warning.message}`).join("；"),
    };
  }
  return { level: "ok", title: "", detail: "" };
}
