// 看板 mod 的纯逻辑测试：node --test tools/tests/test_opc_dashboard_mod.mjs
// model.js 是 ES module，但模版仓没有 package.json，直接 import 文件会被当成
// CommonJS；用 data: URL 导入，测的是同一份源码。
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const source = await readFile(
  path.join(here, "..", "..", "mods", "opc-dashboard", "model.js"),
  "utf8",
);
const model = await import(
  `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`
);

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
        status: "ready",
        role: "content",
        priority: null,
        blocked: false,
        target_date: null,
        created_at: "2026-11-18T09:00:00+08:00",
        approval_status: null,
        publication_ids: ["publication-1"],
        source_path: "knowledge/content/content-1/内容卡.md",
        draft_path: "knowledge/content/content-1/主稿.md",
      },
      {
        content_id: "content-2",
        title: "已关闭的选题",
        status: "closed",
        role: "content",
        priority: null,
        blocked: false,
        target_date: null,
        created_at: "2026-11-01T09:00:00+08:00",
        approval_status: null,
        publication_ids: [],
        source_path: "knowledge/content/content-2/内容卡.md",
        draft_path: "knowledge/content/content-2/主稿.md",
      },
      {
        content_id: "content-3",
        title: "受阻的选题",
        status: "drafting",
        role: "content",
        priority: "high",
        blocked: true,
        block_reason: "缺素材",
        target_date: null,
        created_at: "2026-11-19T09:00:00+08:00",
        approval_status: null,
        publication_ids: [],
        source_path: "knowledge/content/content-3/内容卡.md",
        draft_path: "knowledge/content/content-3/主稿.md",
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
        metrics: { state: "recorded", summary: "48h：views=1234", windows: [] },
        needs_metrics: false,
        needs_review: true,
        review: { status: null, conclusion: null, recorded_at: null },
        source_path: "knowledge/content/content-1/publications/publication-1/发布卡.md",
        draft_path:
          "knowledge/content/content-1/publications/publication-1/渠道稿.md",
      },
      {
        publication_id: "publication-2",
        content_id: "content-1",
        channel: "x",
        status: "scheduled",
        role: "gm",
        priority: null,
        blocked: false,
        created_at: "2026-11-19T09:00:00+08:00",
        planned_at: "2026-11-25T09:00:00+08:00",
        published_at: null,
        url: null,
        approval_status: "approved",
        metrics: { state: "not_applicable", summary: "", windows: [] },
        needs_metrics: false,
        needs_review: false,
        review: { status: null, conclusion: null, recorded_at: null },
        source_path: "knowledge/content/content-1/publications/publication-2/发布卡.md",
        draft_path:
          "knowledge/content/content-1/publications/publication-2/渠道稿.md",
      },
    ],
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
      {
        task_id: "task-done",
        role: "content",
        requester: "gm",
        requested_at: "2026-11-02 09:30",
        task: "修掉旧日历",
        acceptance: "已删除",
        state: "done",
        reason: null,
        source_path: "knowledge/inbox/content.md",
      },
    ],
    approvals: [
      {
        entity: "publication",
        id: "publication-2",
        artifact: "渠道稿.md",
        requested_at: "2026-11-19T10:00:00+08:00",
        requested_by: "content",
        source_path:
          "knowledge/content/content-1/publications/publication-2/发布卡.md",
      },
    ],
    channels: [
      {
        channel: "wechat",
        name: "公众号",
        publication_count: 1,
        account_metrics: { followers: 5000 },
      },
      {
        channel: "x",
        name: "X",
        publication_count: 1,
        account_metrics: {},
      },
    ],
    team: [{ role: "gm", terminal: "opc-gm" }],
    diagnostics: { errors: [], warnings: [] },
    scope: {
      content_ids: ["content-1"],
      publication_ids: ["publication-1"],
      task_ids: ["task-abc"],
      approval_ids: ["publication-2"],
    },
    ...overrides,
  };
}

test("parseDashboard 接受合法契约", () => {
  const parsed = model.parseDashboard(JSON.stringify(payload()));
  assert.equal(parsed.ok, true);
  assert.equal(parsed.payload.contract_version, 1);
});

test("parseDashboard 拒绝空内容、坏 JSON 与错版本", () => {
  const empty = model.parseDashboard("");
  assert.equal(empty.ok, false);
  assert.match(empty.error, /空的/);

  const broken = model.parseDashboard("{not json");
  assert.equal(broken.ok, false);
  assert.match(broken.error, /JSON/);

  const wrong = model.parseDashboard(JSON.stringify({ contract_version: 99 }));
  assert.equal(wrong.ok, false);
  assert.match(wrong.error, /版本/);
});

test("默认视图不含历史，历史要显式打开", () => {
  const view = model.applyFilters(payload(), model.emptyFilters());
  assert.deepEqual(
    view.contents.map(content => content.content_id),
    ["content-1", "content-3"],
  );
  assert.equal(view.tasks.length, 1);

  const withHistory = model.applyFilters(payload(), {
    ...model.emptyFilters(),
    includeHistory: true,
  });
  assert.equal(withHistory.contents.length, 3);
  assert.equal(withHistory.tasks.length, 2);
});

test("筛选支持渠道、内容状态、发布状态、角色、优先级与阻塞", () => {
  const byChannel = model.applyFilters(payload(), {
    ...model.emptyFilters(),
    channel: "x",
  });
  assert.deepEqual(
    byChannel.publications.map(publication => publication.publication_id),
    ["publication-2"],
  );
  assert.deepEqual(
    byChannel.contents.map(content => content.content_id),
    ["content-1"],
  );

  const byContentStatus = model.applyFilters(payload(), {
    ...model.emptyFilters(),
    contentStatus: "drafting",
  });
  assert.deepEqual(
    byContentStatus.contents.map(content => content.content_id),
    ["content-3"],
  );

  const byPublicationStatus = model.applyFilters(payload(), {
    ...model.emptyFilters(),
    publicationStatus: "scheduled",
  });
  assert.deepEqual(
    byPublicationStatus.publications.map(publication => publication.publication_id),
    ["publication-2"],
  );

  const byRole = model.applyFilters(payload(), {
    ...model.emptyFilters(),
    role: "gm",
  });
  assert.deepEqual(
    byRole.publications.map(publication => publication.publication_id),
    ["publication-1", "publication-2"],
  );
  assert.equal(byRole.contents.length, 0);

  const byPriority = model.applyFilters(payload(), {
    ...model.emptyFilters(),
    priority: "high",
  });
  assert.deepEqual(
    byPriority.contents.map(content => content.content_id),
    ["content-3"],
  );

  const byBlocked = model.applyFilters(payload(), {
    ...model.emptyFilters(),
    blocked: "yes",
  });
  assert.deepEqual(
    byBlocked.contents.map(content => content.content_id),
    ["content-3"],
  );
});

test("时间筛选按数据截止时间取窗口", () => {
  const recent = model.applyFilters(payload(), {
    ...model.emptyFilters(),
    time: "7d",
  });
  assert.deepEqual(
    recent.contents.map(content => content.content_id),
    ["content-1", "content-3"],
  );

  const older = model.applyFilters(payload(), {
    ...model.emptyFilters(),
    time: "30d",
  });
  assert.equal(older.contents.length, 2);
});

test("紧急项汇总受阻内容、缺指标、缺复盘与待审批", () => {
  const items = model.urgentItems(model.applyFilters(payload(), model.emptyFilters()));
  const kinds = items.map(item => `${item.kind}:${item.id}`).sort();
  assert.deepEqual(kinds, [
    "approval:publication-2",
    "blocked:content-3",
    "review:publication-1",
  ]);
  const blocked = items.find(item => item.kind === "blocked");
  assert.equal(blocked.detail, "缺素材");
  assert.equal(blocked.source_path, "knowledge/content/content-3/内容卡.md");
});

test("内容流水线按状态分组", () => {
  const stages = model.pipeline(model.applyFilters(payload(), model.emptyFilters()));
  assert.deepEqual(
    stages.map(stage => stage.status),
    ["drafting", "ready"],
  );
  assert.equal(stages[1].items.length, 1);
});

test("发布节奏分开计划与已发布", () => {
  const calendar = model.publicationCalendar(
    model.applyFilters(payload(), model.emptyFilters()),
  );
  assert.deepEqual(
    calendar.scheduled.map(publication => publication.publication_id),
    ["publication-2"],
  );
  assert.deepEqual(
    calendar.published.map(publication => publication.publication_id),
    ["publication-1"],
  );
});

test("待 owner 处理的是开放任务与待审批", () => {
  const pending = model.pendingForOwner(
    model.applyFilters(payload(), model.emptyFilters()),
  );
  assert.deepEqual(
    pending.map(item => item.kind),
    ["approval", "task"],
  );
  assert.equal(pending[1].title, "产出本周选题清单");
});

test("渠道增长带账号级指标", () => {
  const growth = model.channelGrowth(
    model.applyFilters(payload(), model.emptyFilters()),
    model.emptyFilters(),
  );
  assert.deepEqual(
    growth.map(channel => channel.channel),
    ["wechat", "x"],
  );
  assert.equal(growth[0].account_metrics.followers, 5000);
});

test("复盘清单带结论占位", () => {
  const reviews = model.reviewItems(model.applyFilters(payload(), model.emptyFilters()));
  assert.equal(reviews.length, 1);
  assert.equal(reviews[0].needs_review, true);
  assert.equal(reviews[0].conclusion, "");
});

test("生成视图的变化不触发 build，canonical 变化触发", () => {
  assert.equal(
    model.shouldRebuild(["knowledge/business/dashboard.json"]),
    false,
  );
  assert.equal(
    model.shouldRebuild(["knowledge/business/wechat/发布记录.md"]),
    false,
  );
  assert.equal(
    model.shouldRebuild(["knowledge/business/选题日历.md"]),
    false,
  );
  assert.equal(
    model.shouldRebuild(["knowledge/content/content-1/内容卡.md"]),
    true,
  );
  assert.equal(model.shouldRebuild(["knowledge/inbox/gm.md"]), true);
  assert.equal(
    model.shouldRebuild(["knowledge/business/growth/渠道快照.md"]),
    true,
  );
  assert.equal(model.shouldRebuild(["knowledge/work/gm/草稿.md"]), false);
  assert.equal(model.shouldRebuild(["knowledge/daily/2026-11-05.md"]), false);
});

test("banner 分辨 warning、error 与 stale", () => {
  const ok = model.bannerState(payload(), { stale: false, changed: [] });
  assert.equal(ok.level, "ok");

  const warned = model.bannerState(
    payload({
      diagnostics: {
        errors: [],
        warnings: [{ source: "knowledge/content/content-1/指标.md", message: "缺窗口" }],
      },
    }),
    { stale: false, changed: [] },
  );
  assert.equal(warned.level, "warning");
  assert.match(warned.detail, /缺窗口/);

  const failed = model.bannerState(
    payload({
      diagnostics: {
        errors: [{ source: "knowledge/content/content-2/内容卡.md", message: "坏了" }],
        warnings: [],
      },
    }),
    { stale: false, changed: [] },
  );
  assert.equal(failed.level, "error");
  assert.match(failed.detail, /坏了/);

  const stale = model.bannerState(payload(), {
    stale: true,
    changed: ["knowledge/content/content-1/内容卡.md"],
  });
  assert.equal(stale.level, "warning");
  assert.match(stale.detail, /内容卡/);
});

test("缓存过期只认真实进契约的源文件", () => {
  const instance = "/instance";
  const dashboard = `${instance}/knowledge/business/dashboard.json`;
  const onlyGenerated = model.staleState(
    [
      dashboard,
      `${instance}/knowledge/business/选题日历.md`,
      `${instance}/knowledge/business/wechat/发布记录.md`,
      `${instance}/knowledge/daily/2026-11-05.md`,
      `${instance}/knowledge/work/gm/草稿.md`,
    ],
    dashboard,
  );
  assert.equal(onlyGenerated.stale, false);
  assert.deepEqual(onlyGenerated.changed, []);

  const canonical = model.staleState(
    [...onlyGenerated.changed, `${instance}/knowledge/content/content-1/内容卡.md`],
    dashboard,
  );
  assert.equal(canonical.stale, true);
  assert.deepEqual(canonical.changed, [
    `${instance}/knowledge/content/content-1/内容卡.md`,
  ]);
});

test("源文件路径只允许 canonical 子树，越界写法一律拒绝", () => {
  assert.equal(
    model.isAllowedSourcePath("knowledge/content/content-1/内容卡.md"),
    true,
  );
  assert.equal(
    model.isAllowedSourcePath("knowledge/inbox/gm.md"),
    true,
  );
  assert.equal(
    model.isAllowedSourcePath("knowledge/business/growth/渠道快照.md"),
    true,
  );
  assert.equal(model.isAllowedSourcePath("/etc/passwd"), false);
  assert.equal(model.isAllowedSourcePath("knowledge/content/../../etc/passwd"), false);
  assert.equal(model.isAllowedSourcePath("../../etc/passwd"), false);
  assert.equal(model.isAllowedSourcePath("knowledge/business/dashboard.json"), false);
  assert.equal(model.isAllowedSourcePath(""), false);
  assert.equal(model.isAllowedSourcePath(null), false);
});

test("build 失败时的诊断能解析成可点击的条目", () => {
  const stderr = [
    "警告：knowledge/content/content-1/指标.md：published publication 尚未记录指标窗口",
    "错误：knowledge/content/content-2/内容卡.md：frontmatter 不是合法 JSON",
    "",
  ].join("\n");
  const entries = model.parseBuildDiagnostics(stderr);
  assert.equal(entries.length, 2);
  assert.deepEqual(entries[0], {
    level: "warning",
    source: "knowledge/content/content-1/指标.md",
    message: "published publication 尚未记录指标窗口",
  });
  assert.equal(entries[1].level, "error");
  assert.equal(entries[1].source, "knowledge/content/content-2/内容卡.md");
});

test("空实例给出空状态而不是伪数据", () => {
  const empty = payload({
    contents: [],
    publications: [],
    tasks: [],
    approvals: [],
    channels: [],
  });
  const view = model.applyFilters(empty, model.emptyFilters());
  assert.equal(model.isEmpty(view), true);
  assert.equal(view.counts.contents, 0);
  assert.deepEqual(model.urgentItems(view), []);
  assert.deepEqual(model.pipeline(view), []);
});

test("筛选选项来自契约里的实际取值", () => {
  const options = model.filterOptions(payload());
  assert.deepEqual(options.channels, ["wechat", "x"]);
  assert.deepEqual(options.contentStatuses, ["closed", "drafting", "ready"]);
  assert.deepEqual(options.publicationStatuses, ["published", "scheduled"]);
  assert.deepEqual(options.roles, ["content", "gm"]);
  assert.deepEqual(options.priorities, ["high"]);
});
