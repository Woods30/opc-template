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

// canonical 事实源：只有它们变了才需要重跑 build。work/ 与 daily/ 是过程与日志。
export const CANONICAL_PREFIXES = [
  "knowledge/content/",
  "knowledge/inbox/",
  "knowledge/business/growth/",
];

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

export function pipeline(view) {
  const order = ["proposed", "drafting", "reviewing", "ready", "closed", "cancelled"];
  const buckets = new Map(order.map(status => [status, []]));
  for (const content of view.contents) {
    const status = content.status || "proposed";
    if (!buckets.has(status)) buckets.set(status, []);
    buckets.get(status).push(content);
  }
  return order
    .filter(status => buckets.get(status).length > 0)
    .map(status => ({ status, items: buckets.get(status) }));
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
