// OPC 业务看板：只读展示 canonical 记录编译出的 Dashboard JSON。
// 不做业务写入：状态转换、审批、指标记录都还在 CLI 里，这里只看。
import { View, div } from "gpui-kit";
import { h_flex, v_flex, TextView } from "gpui-base";
import {
  props,
  theme,
  run,
  exec,
  readTextFile,
  watchFolder,
  terminals,
} from "herdr";
import {
  parseDashboard,
  applyFilters,
  emptyFilters,
  filterOptions,
  counts,
  diagnostics,
  urgentItems,
  pipeline,
  publicationCalendar,
  pendingForOwner,
  channelGrowth,
  reviewItems,
  shouldRebuild,
  staleState,
  parseBuildDiagnostics,
  bannerState,
  isEmpty,
  isAllowedSourcePath,
} from "./model.js";

const DASHBOARD_RELATIVE = "knowledge/business/dashboard.json";
const KNOWLEDGE_RELATIVE = "knowledge";
const REFRESH_INTERVAL = 30000;
const DEBOUNCE_MS = 400;
const POLL_INTERVAL = 300;

// 看板只读这些子树里的 canonical 记录；别的路径一律不读。
const SOURCE_PREFIXES = [
  "knowledge/content/",
  "knowledge/inbox/",
  "knowledge/business/growth/",
];

function joinPath(root, relative) {
  return `${root.replace(/\/+$/, "")}/${relative}`;
}

// 源文件路径来自生成的契约，但不能直接拼进 readTextFile：
// 先按字面量拒绝越界写法，再用 realpath 确认解析后的目标仍在实例目录内。
// mod 的 fs/promises 没有 realpath，用实例本来就需要的 python3 做这一步。
const REALPATH_SNIPPET = [
  "import os, sys",
  "base = os.path.realpath(sys.argv[1])",
  "target = os.path.realpath(os.path.join(base, sys.argv[2]))",
  "if target != base and not target.startswith(base + os.sep):",
  "    sys.exit('源文件越出实例目录')",
  "print(target)",
].join("\n");

async function readCanonicalSource(instance, relativePath) {
  if (!isAllowedSourcePath(relativePath)) {
    throw new Error(`源文件路径不在允许范围内：${relativePath}`);
  }
  const result = await exec("python3", [
    "-c",
    REALPATH_SNIPPET,
    instance,
    relativePath,
  ]);
  if (result.code !== 0) {
    throw new Error((result.stderr || "定位源文件失败").trim().slice(0, 200));
  }
  const candidate = String(result.stdout || "").trim();
  if (!candidate) {
    throw new Error("定位源文件失败：没有拿到路径");
  }
  return readTextFile(candidate);
}

export default class OpcDashboard extends View {
  init(_props, cx) {
    this.instance = props()?.instance ?? "";
    this.cx = cx;
    this.payload = null;
    this.error = "";
    this.actionError = "";
    this.buildErrors = [];
    this.filters = emptyFilters();
    this.changed = [];
    this.preview = null;
    this.pending = null;
    this.pendingAt = 0;
    this.building = false;
    this.load(cx);
    cx.timer.every(POLL_INTERVAL, cx => this.pump(cx));
    cx.timer.every(REFRESH_INTERVAL, cx => this.load(cx));
    if (this.instance) this.watch(cx);
  }

  // 文件变化：先合并成一次动作，再决定是重跑 build 还是只重读缓存。
  watch(cx) {
    const folder = joinPath(this.instance, KNOWLEDGE_RELATIVE);
    cx.spawn(async cx => {
      for (;;) {
        let changed = [];
        try {
          changed = await watchFolder(folder);
        } catch (error) {
          return;
        }
        this.changed = Array.isArray(changed) ? changed : [];
        this.pending = shouldRebuild(this.changed) ? "rebuild" : "reload";
        this.pendingAt = Date.now();
      }
    });
  }

  pump(cx) {
    if (!this.pending) return;
    if (Date.now() - this.pendingAt < DEBOUNCE_MS) return;
    const action = this.pending;
    this.pending = null;
    if (action === "rebuild") this.rebuild(cx);
    else this.load(cx);
  }

  async load(cx) {
    if (!this.instance) {
      this.error = "看板不知道实例目录：请从 OPC 布局打开这个面板";
      cx.notify();
      return;
    }
    const path = joinPath(this.instance, DASHBOARD_RELATIVE);
    let text = "";
    try {
      text = await readTextFile(path);
    } catch (error) {
      this.error = `读不到看板缓存（${path}）：${error?.message ?? error}`;
      cx.notify();
      return;
    }
    const parsed = parseDashboard(text);
    if (!parsed.ok) {
      this.error = parsed.error;
      cx.notify();
      return;
    }
    this.error = "";
    this.payload = parsed.payload;
    cx.notify();
  }

  // build 只重生成视图，不改业务事实；同一时刻只跑一个，跑完还有变化就再跑一次。
  async rebuild(cx) {
    if (this.building) {
      this.pending = "rebuild";
      this.pendingAt = Date.now();
      return;
    }
    this.building = true;
    const tool = joinPath(this.instance, "tools/opc-workflow");
    try {
      const result = await exec("python3", [tool, "build"], { cwd: this.instance });
      if (result.code !== 0) {
        this.buildErrors = parseBuildDiagnostics(result.stderr);
        this.actionError = `build 失败：${this.buildErrors.length ? this.buildErrors[0].message : (result.stderr || "").trim().slice(0, 300)}`;
      } else {
        this.actionError = "";
        this.buildErrors = [];
        // 缓存刚重建：之前记下的「源文件变了」已经反映进去了
        this.changed = [];
      }
    } catch (error) {
      this.actionError = `build 失败：${error?.message ?? error}`;
    } finally {
      this.building = false;
    }
    await this.load(cx);
  }

  view() {
    return this.payload ? applyFilters(this.payload, this.filters) : null;
  }

  openSource(sourcePath) {
    if (!sourcePath || !this.instance) {
      this.actionError = "这一条没有可打开的源文件";
      this.cx.notify();
      return;
    }
    // canonical 源文件直接在这里读出来看：看板是只读的，不去改它。
    this.readPreview(sourcePath);
  }

  async readPreview(sourcePath) {
    try {
      const text = await readCanonicalSource(this.instance, sourcePath);
      if (text === null || text === undefined) {
        this.preview = { path: sourcePath, text: "", error: "这个源文件已经不在了" };
      } else {
        const limit = 20000;
        this.preview = {
          path: sourcePath,
          text:
            text.length > limit
              ? `${text.slice(0, limit)}\n\n…（预览到此截断，完整内容见源文件）`
              : text,
          error: "",
        };
      }
      this.actionError = "";
    } catch (error) {
      this.preview = {
        path: sourcePath,
        text: "",
        error: `打不开源文件：${error?.message ?? error}`,
      };
    }
    this.cx.notify();
  }

  // 实例前缀：主布局名就是前缀，终端面板只在那里。
  async instancePrefix() {
    if (!this.instance) return "";
    try {
      const text = await readTextFile(joinPath(this.instance, ".opc/prefix"));
      return String(text || "").trim();
    } catch (error) {
      return "";
    }
  }

  // 终端名来自实例名册，不按命名规则猜地址。
  async focusTerminal(role) {
    const entry = (this.payload?.team ?? []).find(item => item.role === role);
    if (!entry) {
      this.actionError = `名册里没有角色「${role}」的终端`;
      this.cx.notify();
      return;
    }
    try {
      const result = await exec("hc", ["get", entry.terminal, "--json"]);
      if (result.code !== 0) {
        this.actionError = `终端「${entry.terminal}」不在线：${(result.stderr || "").trim().slice(0, 200)}`;
        this.cx.notify();
        return;
      }
      const parsed = JSON.parse(result.stdout || "{}");
      if (!parsed.address) {
        this.actionError = `终端「${entry.terminal}」没有地址`;
        this.cx.notify();
        return;
      }
      this.actionError = "";
      // 看板布局里没有终端面板：先把窗口切回本实例的主布局，
      // 聚焦才有地方显示，否则点了像没反应。
      const prefix = await this.instancePrefix();
      if (prefix) run("layout.switch", { name: prefix });
      run("pane.focus", { terminal: parsed.address });
    } catch (error) {
      this.actionError = `聚焦终端失败：${error?.message ?? error}`;
      this.cx.notify();
    }
  }

  toggleFilter(key, value) {
    const next = { ...this.filters };
    next[key] = next[key] === value ? "" : value;
    this.filters = next;
  }

  toggleHistory() {
    this.filters = { ...this.filters, includeHistory: !this.filters.includeHistory };
  }

  header(t) {
    const payload = this.payload;
    const counted = counts(payload);
    const stamp = this.building ? "正在刷新…" : `数据截止 ${payload.as_of ?? "—"}`;
    return h_flex()
      .items_center()
      .gap(12)
      .px(14)
      .py(10)
      .border_b(1)
      .border_color(t.border)
      .child(div().text_size(14).font_weight(600).text_color(t.foreground).child("OPC 看板"))
      .child(div().text_size(11.5).text_color(t.muted).child(stamp))
      .child(
        div()
          .text_size(11.5)
          .text_color(t.muted)
          .child(
            `内容 ${counted.contents} · 发布 ${counted.publications} · 任务 ${counted.tasks} · 待审批 ${counted.approvals}`,
          ),
      )
      .child(div().flex_1())
      .child(
        div()
          .id("opc-dashboard-refresh")
          .cursor_pointer()
          .text_size(11.5)
          .text_color(t.accent)
          .on_click((_event, cx) => {
            this.rebuild(cx);
          })
          .child("刷新"),
      );
  }

  banner(t) {
    const stale = staleState(this.changed, joinPath(this.instance, DASHBOARD_RELATIVE));
    const state = this.payload
      ? bannerState(this.payload, stale)
      : { level: "error", title: this.error || "看板还没有数据", detail: "" };
    const level = this.actionError || this.buildErrors.length ? "error" : state.level;
    const title = this.actionError ? this.actionError : state.title;
    const detail = this.actionError ? "" : state.detail;
    if (level === "ok" && !title) return null;
    const color = level === "error" ? t.blocked : level === "warning" ? t.working : t.muted;
    const entries = this.payload ? this.diagnosticEntries(level) : [];
    return v_flex()
      .gap(4)
      .px(14)
      .py(8)
      .bg(level === "error" ? t.surface : t.chrome)
      .border_b(1)
      .border_color(t.border)
      .child(div().text_size(11.5).text_color(color).child(title))
      .when(Boolean(detail), el => el.child(div().text_size(11).text_color(t.dim).child(detail)))
      .children(
        entries.map(entry =>
          h_flex()
            .items_center()
            .gap(8)
            .px(6)
            .py(2)
            .rounded(4)
            .bg(t.surface)
            .cursor_pointer()
            .on_click((_event, cx) => {
              this.openSource(entry.source);
              cx.notify();
            })
            .child(div().text_size(11).text_color(t.muted).child(entry.source))
            .child(div().flex_1())
            .child(div().text_size(11).text_color(t.dim).child(entry.message)),
        ),
      );
  }

  // 诊断条目带源文件路径：点一下就能打开那条记录。
  diagnosticEntries(level) {
    if (this.buildErrors.length) {
      return this.buildErrors.map(entry => ({
        source: entry.source,
        message: entry.message,
      }));
    }
    const { errors, warnings } = diagnostics(this.payload);
    const source = level === "error" ? errors : warnings;
    return source
      .filter(entry => entry && typeof entry.source === "string" && entry.source !== "")
      .map(entry => ({ source: entry.source, message: entry.message ?? "" }));
  }

  chip(t, label, active, onClick) {
    return div()
      .id(`opc-dashboard-chip-${label}`)
      .cursor_pointer()
      .text_size(11)
      .rounded(4)
      .px(6)
      .py(2)
      .bg(active ? t.selection : t.surface)
      .text_color(active ? t.foreground : t.muted)
      .on_click((_event, cx) => {
        onClick();
        cx.notify();
      })
      .child(label);
  }

  filterBar(t) {
    const options = filterOptions(this.payload);
    // entries 是 [值, 显示名]：值用于过滤，显示名给人看。
    const group = (label, entries, key, current) =>
      h_flex()
        .items_center()
        .gap(4)
        .child(div().text_size(11).text_color(t.dim).child(label))
        .children(
          entries.map(([value, text]) =>
            this.chip(t, text, current === value, () => this.toggleFilter(key, value)),
          ),
        );
    const timeEntries = [
      ["7d", "7 天"],
      ["30d", "30 天"],
      ["90d", "90 天"],
    ];
    return v_flex()
      .gap(6)
      .px(14)
      .py(8)
      .border_b(1)
      .border_color(t.border)
      .child(
        h_flex()
          .items_center()
          .gap(14)
          .flex_wrap()
          .child(group("时间", timeEntries, "time", this.filters.time))
          .child(
            group(
              "渠道",
              options.channels.map(value => [value, value]),
              "channel",
              this.filters.channel,
            ),
          )
          .child(
            group(
              "内容状态",
              options.contentStatuses.map(value => [value, value]),
              "contentStatus",
              this.filters.contentStatus,
            ),
          )
          .child(
            group(
              "发布状态",
              options.publicationStatuses.map(value => [value, value]),
              "publicationStatus",
              this.filters.publicationStatus,
            ),
          )
          .child(
            group(
              "角色",
              options.roles.map(value => [value, value]),
              "role",
              this.filters.role,
            ),
          )
          .child(
            group(
              "优先级",
              options.priorities.map(value => [value, value]),
              "priority",
              this.filters.priority,
            ),
          )
          .child(
            group(
              "阻塞",
              [
                ["yes", "受阻"],
                ["no", "未受阻"],
              ],
              "blocked",
              this.filters.blocked,
            ),
          ),
      )
      .child(
        h_flex()
          .items_center()
          .gap(8)
          .child(
            this.chip(t, "含历史（closed / archived）", this.filters.includeHistory, () =>
              this.toggleHistory(),
            ),
          ),
      );
  }

  section(t, title, children) {
    return v_flex()
      .gap(6)
      .child(div().text_size(11.5).text_color(t.dim).child(title))
      .children(children);
  }

  row(t, item, onOpen) {
    const clickable = item.source_path ? onOpen : null;
    const row = h_flex()
      .items_center()
      .gap(8)
      .px(8)
      .py(4)
      .rounded(4)
      .bg(t.surface)
      .child(div().text_size(11.5).text_color(t.foreground).child(item.title || item.id))
      .child(div().flex_1())
      .child(div().text_size(11).text_color(t.muted).child(item.detail || ""));
    if (clickable) {
      row.cursor_pointer().on_click((_event, cx) => {
        clickable();
        cx.notify();
      });
    }
    return row;
  }

  urgentColumn(t, view) {
    const items = urgentItems(view);
    const owner = pendingForOwner(view);
    const growth = channelGrowth(view, this.filters);
    return v_flex()
      .gap(14)
      .children([
        this.section(
          t,
          `紧急项（${items.length}）`,
          items.length
            ? items.map(item => this.row(t, item, () => this.openSource(item.source_path)))
            : [div().text_size(11.5).text_color(t.dim).child("没有紧急项")],
        ),
        this.section(
          t,
          `待 owner / gm 处理（${owner.length}）`,
          owner.length
            ? owner.map(item => this.row(t, item, () => this.openSource(item.source_path)))
            : [div().text_size(11.5).text_color(t.dim).child("没有待处理事项")],
        ),
        this.section(
          t,
          "渠道增长",
          growth.length
            ? growth.map(channel =>
                h_flex()
                  .items_center()
                  .gap(8)
                  .px(8)
                  .py(4)
                  .rounded(4)
                  .bg(t.surface)
                  .child(
                    div()
                      .text_size(11.5)
                      .text_color(t.foreground)
                      .child(`${channel.name}（${channel.channel}）`),
                  )
                  .child(div().flex_1())
                  .child(
                    div()
                      .text_size(11)
                      .text_color(t.muted)
                      .child(
                        Object.entries(channel.account_metrics)
                          .map(([key, value]) => `${key}=${value}`)
                          .join("、") || `发布 ${channel.publication_count} 条`,
                      ),
                  ),
              )
            : [div().text_size(11.5).text_color(t.dim).child("没有渠道数据")],
        ),
      ]);
  }

  mainColumn(t, view) {
    const stages = pipeline(view);
    const calendar = publicationCalendar(view);
    const reviews = reviewItems(view);
    const team = this.payload?.team ?? [];
    const agents = terminals();
    return v_flex()
      .gap(14)
      .children([
        this.section(
          t,
          "内容流水线",
          stages.length
            ? stages.map(stage =>
                v_flex()
                  .gap(4)
                  .child(
                    div()
                      .text_size(11)
                      .text_color(t.muted)
                      .child(`${stage.status}（${stage.items.length}）`),
                  )
                  .children(
                    stage.items.map(content =>
                      h_flex()
                        .items_center()
                        .gap(8)
                        .px(8)
                        .py(3)
                        .rounded(4)
                        .bg(t.surface)
                        .cursor_pointer()
                        .on_click((_event, cx) => {
                          this.openSource(content.source_path);
                          cx.notify();
                        })
                        .child(
                          div()
                            .text_size(11.5)
                            .text_color(t.foreground)
                            .child(content.title || content.content_id),
                        )
                        .child(div().flex_1())
                        .child(
                          div().text_size(11).text_color(t.dim).child(content.content_id),
                        ),
                    ),
                  ),
              )
            : [div().text_size(11.5).text_color(t.dim).child("没有内容")],
        ),
        this.section(
          t,
          `发布节奏（计划 ${calendar.scheduled.length} / 已发布 ${calendar.published.length}）`,
          [...calendar.scheduled, ...calendar.published].length
            ? [...calendar.scheduled, ...calendar.published].map(publication =>
                h_flex()
                  .items_center()
                  .gap(8)
                  .px(8)
                  .py(4)
                  .rounded(4)
                  .bg(t.surface)
                  .cursor_pointer()
                  .on_click((_event, cx) => {
                    this.openSource(publication.source_path);
                    cx.notify();
                  })
                  .child(
                    div()
                      .text_size(11.5)
                      .text_color(t.foreground)
                      .child(`${publication.channel} · ${publication.publication_id}`),
                  )
                  .child(div().flex_1())
                  .child(
                    div()
                      .text_size(11)
                      .text_color(t.muted)
                      .child(
                        [
                          publication.planned_at ? `计划 ${publication.planned_at}` : "",
                          publication.published_at ? `发布 ${publication.published_at}` : "",
                          publication.metrics?.summary ?? "",
                        ]
                          .filter(Boolean)
                          .join(" · "),
                      ),
                  ),
              )
            : [div().text_size(11.5).text_color(t.dim).child("没有 publication")],
        ),
        this.section(
          t,
          `增长复盘（${reviews.length}）`,
          reviews.length
            ? reviews.map(review =>
                h_flex()
                  .items_center()
                  .gap(8)
                  .px(8)
                  .py(4)
                  .rounded(4)
                  .bg(t.surface)
                  .cursor_pointer()
                  .on_click((_event, cx) => {
                    this.openSource(review.source_path);
                    cx.notify();
                  })
                  .child(
                    div()
                      .text_size(11.5)
                      .text_color(t.foreground)
                      .child(`${review.channel} · ${review.publication_id}`),
                  )
                  .child(div().flex_1())
                  .child(
                    div()
                      .text_size(11)
                      .text_color(t.muted)
                      .child(review.conclusion || (review.needs_review ? "待复盘" : "")),
                  ),
              )
            : [div().text_size(11.5).text_color(t.dim).child("没有待复盘的发布")],
        ),
        this.section(
          t,
          "角色终端（辅助）",
          team.length
            ? team.map(member =>
                h_flex()
                  .items_center()
                  .gap(8)
                  .px(8)
                  .py(3)
                  .rounded(4)
                  .bg(t.surface)
                  .child(
                    div()
                      .text_size(11.5)
                      .text_color(t.foreground)
                      .child(member.role),
                  )
                  .child(div().flex_1())
                  .child(
                    div()
                      .id(`opc-dashboard-role-${member.role}`)
                      .cursor_pointer()
                      .text_size(11)
                      .text_color(t.accent)
                      .on_click((_event, cx) => {
                        this.focusTerminal(member.role);
                        cx.notify();
                      })
                      .child(member.terminal),
                  ),
              )
            : [div().text_size(11.5).text_color(t.dim).child("名册为空")],
        ),
        this.section(
          t,
          `终端状态（辅助，${agents.length}）`,
          [
            h_flex()
              .items_center()
              .gap(8)
              .px(8)
              .py(3)
              .rounded(4)
              .bg(t.surface)
              .child(div().text_size(11.5).text_color(t.foreground).child("存活终端"))
              .child(div().flex_1())
              .child(div().text_size(11).text_color(t.dim).child(String(agents.length))),
          ],
        ),
      ]);
  }

  // 源文件预览：点条目后在这里读出 canonical 原文，只读不改。
  previewPanel(t) {
    const preview = this.preview;
    if (!preview) return null;
    return v_flex()
      .gap(6)
      .px(14)
      .py(8)
      .border_b(1)
      .border_color(t.border)
      .child(
        h_flex()
          .items_center()
          .gap(8)
          .child(div().text_size(11.5).text_color(t.dim).child("源文件"))
          .child(
            div()
              .text_size(11.5)
              .text_color(t.foreground)
              .child(preview.path),
          )
          .child(div().flex_1())
          .child(
            div()
              .id("opc-dashboard-preview-close")
              .cursor_pointer()
              .text_size(11)
              .text_color(t.accent)
              .on_click((_event, cx) => {
                this.preview = null;
                cx.notify();
              })
              .child("关闭"),
          ),
      )
      .when(
        Boolean(preview.error),
        el =>
          el.child(
            div().text_size(11.5).text_color(t.blocked).child(preview.error),
          ),
      )
      .when(
        Boolean(preview.text),
        el =>
          el.child(
            TextView.markdown(`opc-dashboard-preview-${preview.path}`, preview.text)
              .selectable(true)
              .scrollable(true),
          ),
      );
  }

  render() {
    const t = theme();
    const view = this.view();
    if (!this.payload) {
      return v_flex()
        .size_full()
        .gap(8)
        .p(14)
        .child(div().text_size(13).text_color(t.foreground).child("OPC 看板"))
        .child(div().text_size(11.5).text_color(t.muted).child(this.error || "正在读取看板缓存…"));
    }
    return v_flex()
      .size_full()
      .child(this.header(t))
      .child(this.banner(t))
      .child(this.previewPanel(t))
      .child(this.filterBar(t))
      .child(
        h_flex()
          .flex_1()
          .gap(14)
          .p(14)
          .overflow_y_scroll()
          .child(v_flex().w(340).gap(14).child(this.urgentColumn(t, view)))
          .child(v_flex().flex_1().gap(14).child(this.mainColumn(t, view))),
      )
      .when(isEmpty(view), el =>
        el.child(
          div()
            .px(14)
            .pb(10)
            .text_size(11.5)
            .text_color(t.dim)
            .child("当前筛选下没有记录：放宽筛选或先跑一次 tools/opc-workflow build"),
        ),
      );
  }
}
