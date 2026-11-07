// OPC 业务看板：只读展示 canonical 记录编译出的 Dashboard JSON。
// 不做业务写入：状态转换、审批、指标记录都还在 CLI 里，这里只看。
import { View, div } from "gpui-kit";
import { Editor, EditorState, h_flex, v_flex } from "gpui-base";
import {
  props,
  theme,
  run,
  exec,
  readTextFile,
  watchFolder,
  spaces,
  settings,
} from "herdr";
import {
  parseDashboard,
  applyFilters,
  emptyFilters,
  filterOptions,
  counts,
  diagnostics,
  workflowStages,
  currentActions,
  shouldRebuild,
  staleState,
  parseBuildDiagnostics,
  bannerState,
  dashboardState,
  isAllowedSourcePath,
  findTeamTerminal,
  terminalFocusPlan,
  SOURCE_PREFIXES,
  REALPATH_SNIPPET,
} from "./model.js";

const DASHBOARD_RELATIVE = "knowledge/business/dashboard.json";
const KNOWLEDGE_RELATIVE = "knowledge";
const REFRESH_INTERVAL = 30000;
const DEBOUNCE_MS = 400;
const POLL_INTERVAL = 300;
const PREVIEW_LIMIT = 400000;
const PREVIEW_WIDTH = 480;
const STAGE_WIDTH = 260;

const EDITOR_LANGUAGES = {
  js: "javascript",
  json: "json",
  md: "markdown",
  py: "python",
  ts: "typescript",
  yaml: "yaml",
  yml: "yaml",
};

function editorLanguage(path) {
  const extension = String(path || "").split(".").pop().toLowerCase();
  return EDITOR_LANGUAGES[extension] || extension || "text";
}

function joinPath(root, relative) {
  return `${root.replace(/\/+$/, "")}/${relative}`;
}

async function readCanonicalSource(instance, relativePath) {
  if (!isAllowedSourcePath(relativePath)) {
    throw new Error(`源文件路径不在允许范围内：${relativePath}`);
  }
  const result = await exec("python3", [
    "-c",
    REALPATH_SNIPPET,
    instance,
    relativePath,
    ...SOURCE_PREFIXES,
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
    // 全局 mod：布局不再传实例目录，退回到当前 space 的 folder。
    const space = spaces().find(p => p.active);
    this.instance = props()?.instance || space?.folder || "";
    this.cx = cx;
    this.payload = null;
    this.error = "";
    this.actionError = "";
    this.buildErrors = [];
    this.filters = emptyFilters();
    this.changed = [];
    this.preview = null;
    this.previewEditor = null;
    this.previewRequest = 0;
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
    // EditorState 需要 live host context；异步读取放进 task，不能在普通 Promise continuation 里创建。
    return this.cx.spawn(async cx => this.readPreview(sourcePath, cx));
  }

  async readPreview(sourcePath, cx = this.cx) {
    const request = ++this.previewRequest;
    this.previewEditor?.release();
    this.previewEditor = null;
    this.preview = { path: sourcePath, error: "" };
    cx.notify();
    try {
      const text = await readCanonicalSource(this.instance, sourcePath);
      if (request !== this.previewRequest) return;
      if (text === null || text === undefined) {
        this.preview = { path: sourcePath, error: "这个源文件已经不在了" };
      } else if (text.includes("\0")) {
        this.preview = { path: sourcePath, error: "这是二进制文件，不能作为文本查看" };
      } else {
        const value =
          text.length > PREVIEW_LIMIT
            ? `${text.slice(0, PREVIEW_LIMIT)}\n…（文件过大，预览到此截断）`
            : text;
        const t = theme();
        this.previewEditor = EditorState.new({
          language: editorLanguage(sourcePath),
          readonly: true,
          value,
          font_family: settings().font_family,
          font_size: 12,
          syntax: {
            keyword: t.ansi5,
            string: t.ansi2,
            comment: t.dim,
            function: t.ansi4,
            type: t.ansi3,
            number: t.ansi1,
            constant: t.ansi6,
          },
        });
        this.preview = { path: sourcePath, error: "" };
      }
      this.actionError = "";
    } catch (error) {
      if (request !== this.previewRequest) return;
      this.preview = {
        path: sourcePath,
        error: `打不开源文件：${error?.message ?? error}`,
      };
    }
    cx.notify();
  }

  closePreview() {
    this.previewRequest += 1;
    this.previewEditor?.release();
    this.previewEditor = null;
    this.preview = null;
  }

  // 终端名来自实例名册，不按命名规则猜地址。
  async focusTerminal(role) {
    const terminal = findTeamTerminal(this.payload?.team ?? [], role);
    if (!terminal) {
      this.actionError = `名册里没有角色「${role}」的终端`;
      this.cx.notify();
      return;
    }
    try {
      const result = await exec("hc", ["get", terminal, "--json"]);
      if (result.code !== 0) {
        this.actionError = `终端「${terminal}」不在线：${(result.stderr || "").trim().slice(0, 200)}`;
        this.cx.notify();
        return;
      }
      const parsed = JSON.parse(result.stdout || "{}");
      if (!parsed.address) {
        this.actionError = `终端「${terminal}」没有地址`;
        this.cx.notify();
        return;
      }
      this.actionError = "";
      // 看板现在是同一个布局里的 tab，pane.focus 会选中终端所在 tab。
      for (const step of terminalFocusPlan(parsed.address)) {
        run(step.command, step.args);
      }
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
    // 筛选器横向滚动，不再换行挤占业务看板的纵向空间。
    const group = (label, entries, key, current) =>
      h_flex()
        .flex_none()
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
    return h_flex()
      .flex_none()
      .items_center()
      .gap(14)
      .px(14)
      .py(7)
      .overflow_x_scroll()
      .border_b(1)
      .border_color(t.border)
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
      )
      .child(
        this.chip(t, "含历史", this.filters.includeHistory, () => this.toggleHistory()),
      );
  }

  actionStrip(t, view) {
    const labels = {
      approval: "待你审批",
      blocked: "解除阻塞",
      task: "推进任务",
      metrics: "补齐指标",
      review: "完成复盘",
    };
    const actions = currentActions(view);
    return v_flex()
      .flex_none()
      .gap(7)
      .px(14)
      .py(10)
      .border_b(1)
      .border_color(t.border)
      .child(
        h_flex()
          .items_center()
          .gap(8)
          .child(
            div()
              .text_size(12)
              .font_weight(600)
              .text_color(t.foreground)
              .child("当前该做什么"),
          )
          .child(
            div()
              .text_size(11)
              .text_color(t.dim)
              .child(actions.length ? `按优先级排列，共 ${actions.length} 项` : "当前没有待处理事项"),
          ),
      )
      .when(
        actions.length > 0,
        el =>
          el.child(
            h_flex()
              .gap(8)
              .overflow_x_scroll()
              .children(
                actions.map(action =>
                  v_flex()
                    .id(`opc-dashboard-action-${action.kind}-${action.id}`)
                    .w(280)
                    .flex_none()
                    .gap(4)
                    .px(9)
                    .py(7)
                    .rounded(6)
                    .border_1()
                    .border_color(action.kind === "blocked" ? t.blocked : t.border)
                    .bg(t.surface)
                    .cursor_pointer()
                    .on_click((_event, cx) => {
                      this.openSource(action.source_path);
                      cx.notify();
                    })
                    .child(
                      h_flex()
                        .items_center()
                        .gap(7)
                        .child(
                          div()
                            .text_size(10.5)
                            .text_color(action.kind === "blocked" ? t.blocked : t.accent)
                            .child(labels[action.kind] || action.kind),
                        )
                        .child(div().flex_1())
                        .child(div().text_size(10.5).text_color(t.dim).child(action.role || "—")),
                    )
                    .child(
                      div()
                        .text_size(11.5)
                        .font_weight(500)
                        .text_color(t.foreground)
                        .truncate()
                        .child(action.title || action.id),
                    )
                    .when(
                      Boolean(action.detail),
                      card =>
                        card.child(
                          div().text_size(10.5).text_color(t.muted).truncate().child(action.detail),
                        ),
                    ),
                ),
              ),
          ),
      );
  }

  fileLink(t, item, label, path) {
    return div()
      .id(`opc-dashboard-file-${item.kind}-${item.id}-${label}`)
      .cursor_pointer()
      .rounded(4)
      .px(5)
      .py(2)
      .bg(t.chrome)
      .text_size(10.5)
      .text_color(t.accent)
      .on_click((_event, cx) => {
        this.openSource(path);
        cx.notify();
      })
      .child(label);
  }

  stageCard(t, item) {
    const kindLabel = item.kind === "content" ? "内容" : "发布";
    const links = [
      item.source_path ? this.fileLink(t, item, item.kind === "content" ? "内容卡" : "发布卡", item.source_path) : null,
      item.draft_path ? this.fileLink(t, item, item.kind === "content" ? "主稿" : "渠道稿", item.draft_path) : null,
    ].filter(Boolean);
    return v_flex()
      .gap(6)
      .p(9)
      .rounded(6)
      .border_1()
      .border_color(item.blocked ? t.blocked : t.border)
      .bg(t.surface)
      .child(
        h_flex()
          .items_center()
          .gap(7)
          .child(div().text_size(10.5).text_color(t.accent).child(kindLabel))
          .child(div().text_size(10.5).text_color(t.dim).child(item.status))
          .child(div().flex_1())
          .child(div().text_size(10.5).text_color(t.muted).child(item.role || "—")),
      )
      .child(
        div()
          .text_size(11.5)
          .font_weight(500)
          .text_color(t.foreground)
          .child(item.title || item.id),
      )
      .when(
        Boolean(item.blocked),
        card =>
          card.child(
            div()
              .text_size(10.5)
              .text_color(t.blocked)
              .child(item.block_reason || "当前受阻"),
          ),
      )
      .when(links.length > 0, card => card.child(h_flex().gap(5).children(links)));
  }

  stageBoard(t, view) {
    const stages = workflowStages(view);
    return h_flex()
      .flex_1()
      .min_h(0)
      .min_w(0)
      .gap(10)
      .p(12)
      .overflow_x_scroll()
      .children(
        stages.map(stage =>
          v_flex()
            .w(STAGE_WIDTH)
            .flex_none()
            .min_h(0)
            .rounded(7)
            .border_1()
            .border_color(t.border)
            .bg(t.chrome)
            .child(
              v_flex()
                .flex_none()
                .gap(3)
                .px(10)
                .py(9)
                .border_b(1)
                .border_color(t.border)
                .child(
                  h_flex()
                    .items_center()
                    .child(
                      div()
                        .text_size(12)
                        .font_weight(600)
                        .text_color(t.foreground)
                        .child(stage.label),
                    )
                    .child(div().flex_1())
                    .child(
                      div()
                        .text_size(10.5)
                        .text_color(stage.items.length ? t.accent : t.dim)
                        .child(String(stage.items.length)),
                    ),
                )
                .child(div().text_size(10.5).text_color(t.dim).child(stage.hint)),
            )
            .child(
              v_flex()
                .flex_1()
                .min_h(0)
                .gap(8)
                .p(8)
                .overflow_y_scrollbar()
                .when(
                  stage.items.length === 0,
                  column =>
                    column.child(
                      div().text_size(10.5).text_color(t.dim).child("暂无记录"),
                    ),
                )
                .children(stage.items.map(item => this.stageCard(t, item))),
            ),
        ),
      );
  }

  // 源文件在右侧原生 Editor 中展开，保留看板上下文，只读不改。
  previewPanel(t) {
    const preview = this.preview;
    if (!preview) return null;
    return v_flex()
      .w(PREVIEW_WIDTH)
      .flex_none()
      .min_h(0)
      .border_l(1)
      .border_color(t.border)
      .bg(t.background)
      .child(
        v_flex()
          .flex_none()
          .gap(3)
          .px(12)
          .py(9)
          .border_b(1)
          .border_color(t.border)
          .child(
            h_flex()
              .items_center()
              .gap(8)
              .child(
                div()
                  .text_size(11.5)
                  .font_weight(600)
                  .text_color(t.foreground)
                  .child("文件内容"),
              )
              .child(div().flex_1())
              .child(
                div()
                  .id("opc-dashboard-preview-close")
                  .cursor_pointer()
                  .text_size(11)
                  .text_color(t.accent)
                  .on_click((_event, cx) => {
                    this.closePreview();
                    cx.notify();
                  })
                  .child("关闭"),
              ),
          )
          .child(
            div()
              .text_size(10.5)
              .text_color(t.dim)
              .truncate()
              .child(preview.path),
          ),
      )
      .when(
        Boolean(preview.error),
        el =>
          el.child(
            div().p(12).text_size(11.5).text_color(t.blocked).child(preview.error),
          ),
      )
      .when(
        !preview.error && !this.previewEditor,
        el => el.child(div().p(12).text_size(11.5).text_color(t.dim).child("正在读取文件…")),
      )
      .when(
        Boolean(this.previewEditor),
        el => el.child(Editor.new(this.previewEditor).flex_1().min_h(0)),
      );
  }

  // 坏看板：缓存读不到或不是合法 JSON。这是基础设施问题，要红。
  brokenView(t) {
    const loading = !this.error;
    return v_flex()
      .size_full()
      .gap(8)
      .p(14)
      .child(div().text_size(13).text_color(t.foreground).child("OPC 看板"))
      .child(
        div()
          .text_size(11.5)
          .text_color(loading ? t.muted : t.blocked)
          .child(
            loading
              ? "正在读取看板缓存…"
              : `读不到看板缓存：${this.error}`,
          ),
      )
      .child(
        div()
          .text_size(11)
          .text_color(t.dim)
          .child(
            loading
              ? "缓存由 tools/opc-workflow build 生成，装完实例就有。"
              : "看板缓存由 tools/opc-workflow build 生成。生成失败多半是某张内容卡写坏了。",
          ),
      )
      .child(
        h_flex()
          .gap(8)
          .child(
            div()
              .id("opc-dashboard-retry")
              .cursor_pointer()
              .text_size(11.5)
              .text_color(t.accent)
              .on_click((_event, cx) => {
                this.load(cx);
              })
              .child("重试"),
          )
          .child(
            div()
              .id("opc-dashboard-rebuild")
              .cursor_pointer()
              .text_size(11.5)
              .text_color(t.accent)
              .on_click((_event, cx) => {
                this.rebuild(cx);
              })
              .child("重新生成缓存"),
          ),
      );
  }

  // 空看板：缓存是好的，只是业务还没数据。这是正常状态，不该用错误色喊人。
  emptyView(t, state) {
    return v_flex()
      .size_full()
      .child(this.header(t))
      .child(this.filterBar(t))
      .child(
        v_flex()
          .gap(8)
          .p(14)
          .child(div().text_size(12).text_color(t.foreground).child(state.title))
          .child(div().text_size(11.5).text_color(t.muted).child(state.detail))
          .child(
            div()
              .id("opc-dashboard-build")
              .cursor_pointer()
              .text_size(11.5)
              .text_color(t.accent)
              .on_click((_event, cx) => {
                this.rebuild(cx);
              })
              .child("重新生成看板缓存"),
          ),
      );
  }

  render() {
    const t = theme();
    const view = this.view();
    if (!this.payload) {
      return this.brokenView(t);
    }
    const state = dashboardState(this.payload, this.filters);
    if (state) {
      return this.emptyView(t, state);
    }
    // banner() 与 previewPanel() 都会在「没有内容」时返回 null，
    // 而 gpui 的 child() 不接受 null：整块用 when 挂上去，不成立就不挂。
    const banner = this.banner(t);
    const preview = this.previewPanel(t);
    return v_flex()
      .size_full()
      .min_h(0)
      .child(this.header(t))
      .when(Boolean(banner), el => el.child(banner))
      .child(this.filterBar(t))
      .child(this.actionStrip(t, view))
      .child(
        h_flex()
          .flex_1()
          .min_h(0)
          .child(this.stageBoard(t, view))
          .when(Boolean(preview), el => el.child(preview)),
      );
  }
}
