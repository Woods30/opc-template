# Proposed Content Calendar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 提供最小 `opc-workflow` CLI，让 OPC 实例能创建 canonical proposed 内容卡、校验手工编辑结果，并原子生成只读选题日历。

**Architecture:** 使用单个 Python 3 标准库工具承载 CLI、JSON frontmatter parser、validator 与 Markdown adapter；内容卡固定存放在 `knowledge/content/<content_id>/内容卡.md`。命令只面向显式 `--root` 或工具所在实例，`build` 先完整校验并在同目录写临时文件，成功后用 `os.replace` 原子替换日历。

**Tech Stack:** Python 3 standard library、`unittest`、Markdown、JSON-compatible frontmatter。

**Spec:** GitHub Issues [#2](https://github.com/Woods30/opc-template/issues/2) 与 [#1](https://github.com/Woods30/opc-template/issues/1)。

## Global Constraints

- 不引入数据库、服务、daemon、package manager 或第三方 runtime dependency。
- 所有测试只操作 `tempfile.TemporaryDirectory` 创建的隔离 OPC 实例。
- canonical 内容卡从创建起不移动，生成视图不成为第二事实源。
- 时间统一使用 offset-aware ISO 8601；actor 来自 `roles.json` 的 role key。
- 不兼容旧日历作为输入；本 ticket 只生成 proposed 内容的待排期视图。
- 保留工作区现有 Codex hook 相关改动，提交时仅纳入本计划文件。

## Review Focus

- 标题、来源和摘要含 Markdown 表格控制字符或换行时，生成视图必须保持合法表格。
- Python 的 `bool` 不得被误判为整数 schema version。
- 内容目录中的 symlink 不得让 parser 或 writer 逃出实例根目录。
- 已存在有效日历遇到任一无效内容卡时必须字节级保持不变，且不残留临时文件。
- 两次快速创建必须得到不同 ID，且任何一次创建都不得覆盖已有内容包。

---

### Task 1: 创建 proposed 内容卡

**Files:**
- Create: `tools/opc-workflow`
- Create: `tools/tests/test_opc_workflow.py`
- Modify: `roles.json`

**Interfaces:**
- Produces: `tools/opc-workflow --root <实例> create-content --title <标题> [--source <来源>] [--summary <摘要>] [--actor <角色>]`。
- Produces: `content-YYYYMMDD-HHMMSSffffff-<8 hex>` 格式的不可覆盖 ID，以及 `knowledge/content/<id>/内容卡.md`。

- [ ] **Step 1: 写失败的 CLI 集成测试**

覆盖最小创建、可选字段、默认 actor、两次快速创建 ID 不同、固定路径、JSON frontmatter 与 create event，并断言测试实例含合法 `.opc/instance.json` 与 `roles.json`。

- [ ] **Step 2: 运行单文件测试确认 Red**

Run: `python3 tools/tests/test_opc_workflow.py -v`
Expected: 因 `tools/opc-workflow` 不存在而失败。

- [ ] **Step 3: 实现最小 create-content**

`main(argv: list[str] | None) -> int` 解析全局 `--root` 与子命令；`create_content(root, title, source, summary, actor) -> tuple[str, str]` 校验实例与 actor，生成 UTC 时间、唯一目录及内容卡。已存在目录必须重试新 ID，绝不覆盖。

- [ ] **Step 4: 更新角色 scope**

`gm` 与 `content` 增加 `knowledge/content`；content 移除对 generated `knowledge/business/选题日历.md` 的直接写权限。

- [ ] **Step 5: 运行单文件测试确认 Green**

Run: `python3 tools/tests/test_opc_workflow.py -v`
Expected: 创建相关测试全部通过。

### Task 2: 校验手工编辑内容卡

**Files:**
- Modify: `tools/opc-workflow`
- Modify: `tools/tests/test_opc_workflow.py`

**Interfaces:**
- Consumes: Task 1 的 JSON frontmatter schema 与固定内容路径。
- Produces: `parse_content_card(path: str, root: str) -> (record | None, diagnostics)` 与 `validate` 子命令；诊断格式包含 repo-relative source path。

- [ ] **Step 1: 写失败的 validate 集成测试**

分别覆盖空实例、合法手工编辑、损坏 JSON、错误字段类型、未知 schema version、重复 `content_id`、非法 actor、naive/非法时间、目录与 ID 不一致，以及 symlink 内容包；断言退出码与每条诊断的源路径。

- [ ] **Step 2: 运行单文件测试确认 Red**

Run: `python3 tools/tests/test_opc_workflow.py -v`
Expected: `validate` 不存在或错误输入未被拒绝。

- [ ] **Step 3: 实现 parser 与 validator**

schema version 固定为整数 `1`，record type 固定为 `content`；必需字段为 `schema_version`、`record_type`、`content_id`、`title`、`status`、`created_at`、`actor`、`events`。状态固定为 `proposed`，create event 必须匹配顶层时间、actor 与状态；可选 `source`、`summary` 必须为非空字符串。扫描后统一检查重复 ID。

- [ ] **Step 4: 运行单文件测试确认 Green**

Run: `python3 tools/tests/test_opc_workflow.py -v`
Expected: 所有 validation 场景通过。

### Task 3: 原子生成选题日历并同步文档

**Files:**
- Modify: `tools/opc-workflow`
- Modify: `tools/tests/test_opc_workflow.py`
- Modify: `seeds/knowledge/business/选题日历.md`
- Modify: `agents/opc-content.md`
- Modify: `AGENTS.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: Task 2 返回的合法 content records。
- Produces: `build` 子命令与 `knowledge/business/选题日历.md`，包含 generated/read-only/source 标记和“待排期选题”视图。

- [ ] **Step 1: 写失败的 build 集成测试**

覆盖空实例有意义的空视图、proposed 记录按创建时间和 ID 稳定排序、Markdown 字符转义、generated/read-only/source 标记，以及无效记录时旧日历保持不变且无临时文件残留。

- [ ] **Step 2: 运行单文件测试确认 Red**

Run: `python3 tools/tests/test_opc_workflow.py -v`
Expected: `build` 不存在或未满足输出契约。

- [ ] **Step 3: 实现 render 与 atomic replace**

`render_calendar(records: list[dict]) -> str` 只输出 metadata 和 canonical card 链接；`write_atomic(path: str, text: str) -> None` 在目标目录创建临时文件、flush/fsync 后 `os.replace`，任何异常清理临时文件。

- [ ] **Step 4: 更新 seed、角色说明与 README**

把选题日历 seed 改为 generated 空视图；content 角色改为通过 CLI 创建 canonical proposal，不再手工维护日历；文档补齐目录、命令、schema 与只读说明。

- [ ] **Step 5: 运行专项与全量验证**

Run: `python3 tools/tests/test_opc_workflow.py -v`
Expected: 全部通过。

Run: `python3 -m unittest discover -s tools/tests -t . -v`
Expected: 全部 Python tests 通过。

Run: `bash tools/tests/test_opc_sync.sh`
Expected: 退出码 0。

Run: `scripts/opc-lint.sh --strict`
Expected: 退出码 0，无 warning/failure。

- [ ] **Step 6: review 并提交**

执行 `/code-review` 等价 review，修复确认的问题后只暂存 Issue #2 文件，提交消息：`feat: 创建 proposed 内容并生成选题日历`。

## 实现后修订（code review 之后）

review 发现的问题与最终裁定，实现与本计划有出入的地方以此节为准：

- **实例根目录**不再用 `--root` 传入，改由脚本自身位置推导（工具住在 `<实例>/tools/` 下）。
  角色不得把实例外的目录当事实来源。
- **status 与 events** 按内容生命周期校验：`proposed` / `drafting` / `reviewing` / `ready` /
  `closed` / `cancelled`；`events` 允许 create 之后的业务事件，逐条校验时间与 actor。
- **内容包缺少内容卡**是警告，不阻断 `validate`。
- **`build` 拒绝覆盖缺 generated 标记的既有日历**，旧格式日历要人工迁移，不能被静默冲掉。
- **actor 不可冒充**：`OPC_ROLE` 存在时 `--actor` 必须与之一致；停用角色不能创建内容。
- **preflight 在 generated 日历下**把旧日历检查（稿件登记、支柱列）降为「跳过」，
  不再拿旧格式当事实；canonical 内容卡级别的核对由后续迭代接上。
- **安装器白名单**未放行 `Bash(./tools/opc-workflow:*)`：该表是只读命令表，写工具进去
  会绕过 Edit 子树隔离。工具级 scope 校验与放行一起做。
