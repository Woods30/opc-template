# OPC 工程模版

一套**一人公司（One Person Company）的 AI 团队脚手架**：把 gm / content / growth / dev
四个角色做成独立运行的 agent，用文件协作、用消息唤醒。

- 基于 [`herdr-core`](https://github.com/)（`hc`）的模板机制，每个角色一个持久终端
- 在 Herdr 窗口里各占一个 tab，随时可以看、可以接手
- 角色、CLI、可写目录、频道清单全部由 JSON 配置，可增删启停
- **结果与过程分开**：`knowledge/business/` 是老板日常只看的结果，`knowledge/work/` 是过程
- 结论落盘到 `knowledge/`，聊天记录不算数

## 依赖

| 依赖 | 用途 | 检查 |
|---|---|---|
| `hc`（herdr-core） | 终端与角色模板 | `hc --version` |
| `herdr-app` | 窗口与布局 | `herdr-app ls` |
| `claude`（Claude Code） | 默认 agent CLI | `claude --version` |
| `jq` | 脚本解析 JSON | `jq --version` |

## 快速开始

**模版仓库不承载业务数据。** 它只装机制与占位骨架；业务内容一律长在**实例**里。
所以第一步不是在本仓库里装，而是开一个实例：

```sh
git clone <this-repo> ~/Projects/opc-template     # 模版
scripts/opc-new.sh ~/Documents/my-opc             # 开实例
cd ~/Documents/my-opc

scripts/opc-up.sh             # 启动所有已启用角色
scripts/opc-status.sh         # 看状态
scripts/opc-down.sh           # 停止
```

`opc-new.sh` 会建好实例目录、初始化一个**独立的 git 仓库**（业务数据只进这个仓库）、
写 `.opc/instance.json` 记录模版来源，然后跑一次安装。常用参数：

```sh
scripts/opc-new.sh ~/Documents/my-opc acme --prefix acme   # 指定前缀
scripts/opc-new.sh ~/Documents/my-opc --dry-run            # 只看要做什么
```

**不要在模版仓库里跑 `opc-install.sh`**——安装脚本会检测到 `.opc-template-repo`
标记并直接拒绝。模版里也不该出现任何业务文件，`scripts/opc-lint.sh` 会持续检查。

`opc-up.sh` 默认 **fail-closed**：缺模板或启动器就报错退出，不自动执行安装脚本。
脚本属于执行面，agent 不可写（`scripts/` 不在任何角色的 `scope` 内），所以启动时
也不能悄悄把它跑起来。

**推荐路径**：在实例目录启动 Claude Code，输入 `/opc-init`。它会检查依赖、问前缀/角色/
CLI/频道，改好 `roles.json` 与 `channels.json`，跑安装，并跑一次端到端测试任务。

## 一个实例长什么样

```
roles.json           角色注册表：启用/停用、CLI、可写子树、权限模式
channels.json        频道清单：id / 中文名 / 是否启用
AGENTS.md            各角色共用的规约（Claude Code 自动加载）
LESSONS.md           全局经验教训库（gm 维护；角色写各自的 work/<角色>/LESSONS.md）
CLAUDE.md            一行：@AGENTS.md
INSTANCE.md          本实例专属信息（前缀、频道、运行参数、待办）
agents/              各角色的 hc 模板源（唯一事实来源）
seeds/               占位骨架源：开实例时物化到 knowledge/business/
knowledge/           唯一事实来源：
                     ├── content/   canonical 内容包：内容卡、主稿、publications/
                     ├── business/  结果、常驻口径与 generated 只读视图
                     ├── work/      过程：每个角色一个子树（草稿、提案、日志）
                     └── decisions/ inbox/
scripts/             安装、启停、状态、角色管理、同步（执行面，仅 owner 可写）
tools/               只读包装器与校验工具（执行面，仅 owner 可写）
layouts/             Herdr 窗口布局（默认 / focus / grid / monitor）
.opc/                安装脚本生成（不进版本库）
```

**生成物不要手改**：`knowledge/team.md`、`knowledge/business/README.md`、
`knowledge/business/选题日历.md`、`knowledge/inbox/<角色>.md`（首次生成后由角色使用）、
`.opc/**` 都由工具生成。选题日历运行 `tools/opc-workflow build` 刷新，其余文件由
`scripts/opc-install.sh` 生成。

**结果与过程分开**：老板日常只看 `knowledge/business/`；`knowledge/work/` 里的草稿
再多也不会干扰。命名规则：目录是结构用英文，文件是内容用中文。

## 模版与实例

这是本模版最重要的一条纪律：**模版仓库不承载业务数据**。

```text
~/Projects/opc-template     模版（公开仓库 Woods30/opc-template）
                            只装机制与占位骨架；没有任何 knowledge/ 目录
~/Documents/OPC             实例（本地 git，无远端）
                            真实业务 + 实例配置 + 模版的机制副本
```

- 模版根目录的 `.opc-template-repo` 是标记。`opc-install.sh` 与 `opc-sync.sh`
  检测到它就拒绝执行——模版不能变成实例。
- 模版的占位骨架放在 `seeds/knowledge/business/`，开实例时物化到实例的
  `knowledge/business/`；物化之后那份文件就归业务所有。
- `opc-new.sh` 不复制模版的 `knowledge/`（sync-policy 里是 `local`）。实例的内容区由安装器
  创建，业务规则与 generated 视图入口从 `seeds/` 物化，不携带模版工作区的真实业务数据。
- `opc-new.sh` 建实例时写基线快照 `.opc/sync-base/`：没有基线就判不出本地改没改过，
  模版后续的机制更新传不进实例。老实例补基线跑 `scripts/opc-sync.sh baseline --from <模版>`。
- 实例仓库建议**不推任何远端**；业务数据只在本机，另做一个本地裸库镜像备份。
- 模版迭代后同步到实例：`scripts/opc-sync.sh check` 看差异，
  `scripts/opc-sync.sh pull` 拉更新。冲突时业务文件不会被改动，产物在
  `.opc/sync-conflicts/`。
- 实例里发现模版要改，**不要直接改模版文件**：写提案到
  `knowledge/work/<角色>/template-proposals/`，gm 汇总，owner 脱敏后搬进模版仓库。

命令速查：

```sh
scripts/opc-sync.sh status     # 实例摘要：模版来源、上次同步、pinned 数
scripts/opc-sync.sh check      # 这次的变更计划（只读）
scripts/opc-sync.sh pull       # 拉取模版更新
scripts/opc-sync.sh baseline   # 固化基线快照（老实例接入模版时用；不改业务文件）
scripts/opc-sync.sh seeds      # 骨架差异；--merge <目标> 做三方合并
scripts/opc-sync.sh mark <路径> # 固化本地定制，模版此后不覆盖
```

退出码：`0` 成功/无差异；`1` 有差异或失败；`2` 用法/环境错；`3` 有冲突
（业务文件未被改动）。机制细节见 [`docs/同步机制.md`](docs/同步机制.md)。

## 模版自检：opc-lint

公开仓库必须保证没有真实业务。`scripts/opc-lint.sh` 就是这道闸：

```sh
scripts/opc-lint.sh                          # 在模版仓库根跑
scripts/opc-lint.sh --strict                 # 警告也算违规
scripts/opc-lint.sh --private-words ~/.config/opc/private-words.txt
```

检查的内容：模版里没有 `knowledge/**`、种子还是占位而不是真实内容、种子里没有
具体日期/链接/大数、频道清单为空、角色注册表字段合法、策略覆盖了每个文件、
守卫本身在位、模版里没有本机路径、提案格式完整。角色启动那条规则两边都查：
模版里的 `agents/*.md` 与实例里自己的 `agents/*.md` 都要写明「等 gm 派工」
（gm 是「先与 owner 对齐方向」），写成「不用等 gm 派工」这种否定句一样算违规。
私词表**永远不进版本库**，放在实例的 `.opc/private-words.txt` 或
`~/.config/opc/private-words.txt`；CI 用 secret 注入，没有 secret 时该规则自动跳过
而不是失败。

`.github/workflows/lint.yml` 在每次 push 与 PR 上跑它，另跑两组测试：

```sh
python3 tools/tests/test_opc_lint.py    # lint 规则本身
python3 tools/tests/test_preflight.py   # 发布前自检
bash tools/tests/test_opc_sync.sh       # 同步机制的场景回归
```

## 角色是配置

默认四个角色只是初始值。`roles.json` 每条记录：

```json
{
  "name": "growth",
  "enabled": true,
  "cli": "claude",
  "template": "agents/opc-growth.md",
  "permissionMode": "default",
  "scope": [
    "knowledge/work/growth",
    "knowledge/business/growth"
  ]
}
```

| 字段 | 作用 |
|---|---|
| `enabled` | 停用后不生成模板、不启动、不进名册 |
| `cli` | 该角色用哪个 CLI，默认 `claude` |
| `permissionMode` | `default` / `manual` / `auto` / `acceptEdits` / `plan` / `dontAsk`；`bypassPermissions` 被拒绝 |
| `scope` | 允许自动写入的路径：**目录**表示整棵子树（拼 `/**`），**文件**（`.md` 等）表示精确文件 |
| `template` | 角色简报路径 |

用命令改：

```sh
scripts/opc-role.sh list
scripts/opc-role.sh disable growth
scripts/opc-role.sh enable growth
scripts/opc-role.sh add editor --desc "负责润色与事实核查" --scope knowledge/work/editor
scripts/opc-role.sh add reviewer --cli codex --desc "独立审稿" --scope knowledge/work/reviewer
```

启动时也可以只挑一部分：`scripts/opc-up.sh gm content`。

## 频道是配置

`channels.json` 决定 `knowledge/business/` 下有哪些频道目录。模版**不预置频道**——
`/opc-init` 会问你要哪几个，每个频道一个英文 `id`（小写 slug，会直接成为目录名）
和一个中文显示名；暂不做的写 `enabled: false`。

```json
{
  "channels": [
    { "id": "wechat", "name": "公众号", "enabled": true }
  ]
}
```

改完重跑 `scripts/opc-install.sh`：只建启用频道的目录与 `发布记录.md`，**已存在的
目录不删**（避免删掉历史产出）。

## 内容事实入口：tools/opc-workflow

`opc-workflow` 用 Python 3 标准库维护 canonical 内容卡和派生视图，不依赖数据库、服务或
第三方 package。实例根目录由脚本自身位置推导（工具住在 `tools/` 下），不接受外部传入的
根目录，因此只能作用于本实例：

```sh
tools/opc-workflow create-content --title "<标题>" --target-date "<YYYY-MM-DD>"
tools/opc-workflow transition <content_id> --to drafting
tools/opc-workflow transition <content_id> --to reviewing
tools/opc-workflow transition <content_id> --decision approved --actor gm
tools/opc-workflow transition <content_id> --decision changes_requested --note "<修改说明>" --actor gm
tools/opc-workflow create-publication <content_id> --channel <channel> [--required-window 48h ...] [--optional] --actor gm
tools/opc-workflow transition <publication_id> --to reviewing --actor content
tools/opc-workflow transition <publication_id> --decision approved --actor gm
tools/opc-workflow transition <publication_id> --to scheduled --planned-at "<ISO 8601>" --timezone "<IANA timezone>" --actor gm
tools/opc-workflow transition <publication_id> --to scheduled --planned-at "<ISO 8601>" --timezone "<IANA timezone>" --note "<改期原因>" --actor gm
tools/opc-workflow transition <publication_id> --to cancelled --note "<取消原因>" --actor gm
tools/opc-workflow transition <publication_id> --to published --actual-at "<offset-aware ISO 8601>" --url "<HTTP(S) URL>" [--external-id "<平台 ID>"] --actor gm
tools/opc-workflow transition <publication_id> --to reviewed --conclusion <continue|iterate|stop|inconclusive> --next-action "<下一项行动>" --actor growth
tools/opc-workflow transition <content_id> --to closed --actor gm
tools/opc-workflow transition <content_id> --to cancelled --note "<取消原因>" --actor gm
tools/opc-workflow block <content_id> --reason "<阻塞原因>" --actor content
tools/opc-workflow unblock <content_id> [--note "<解除说明>"] --actor gm
tools/opc-workflow record-metrics <publication_id> --window 48h --observed-at "<offset-aware ISO 8601>" --source "<来源>" --values '{"<metric_key>": 数值}' --actor growth
tools/opc-workflow record-channel-snapshot --channel <channel> --observed-at "<offset-aware ISO 8601>" --source "<来源>" --values '{"<metric_key>": 数值}' --actor growth
tools/opc-workflow validate
tools/opc-workflow build
```

`create-content` 生成不可覆盖的 `content_id`，把 JSON-compatible frontmatter 内容卡固定写到
`knowledge/content/<content_id>/内容卡.md`；后续状态变化不移动目录。actor 必须是
`roles.json` 中的 role key，省略时依次取 `OPC_ROLE` 与 `content`；`OPC_ROLE` 存在时不允许
用 `--actor` 冒充别的角色，已停用的角色也不能创建内容。内容卡可以直接编辑，
但编辑后应先运行 `validate`；诊断会指向损坏的源记录。

**actor 是归属记录，不是授权**：`OPC_ROLE` 由角色启动器导出，但调用方自己也能设置它，
工具无法自证调用者是谁。所以这条检查防的是误用（顺手写了别人的角色名），不是伪造；
权限由 owner 为每个角色选择的 CLI 原生模式与用户级配置控制。
`create-content` 每次都会把记下的 actor 打在输出里（`actor=content`），归属写错能当场发现。

`transition --to drafting` 在内容包内创建固定的 `主稿.md`，后续编辑不移动文件；
`--to reviewing` 按主稿原始 bytes 计算 SHA-256 并创建 pending approval。gm 记录 owner 的
`approved`、`changes_requested` 或 `rejected` 决定：只有 approved 进入 ready，另外两种
回到 drafting 且必须带 note。审核请求后、决定前改稿，或 approved 后改稿，会被 `validate`
标为 `stale approval`；`build` 也会拒绝使用失效审批并保留上一份有效日历。退回后的正常
改稿不会把负面决定误判为 stale；重新提交、重新审批后新 hash 生效，旧决定留在 `events`
中。普通文案编辑由 Git 留痕，不产生业务事件。

内容 ready 后，gm 用 `create-publication` 按需创建渠道 publication。每次尝试拥有不可复用的
`publication_id`，固定放在
`knowledge/content/<content_id>/publications/<publication_id>/`，其中 `发布卡.md` 是状态事实，
`渠道稿.md` 是 content 编辑的 canonical 渠道稿。素材按归属分开：跨渠道复用的通用素材放
内容包的 `knowledge/content/<content_id>/assets/`，只在某个渠道用的素材放该 publication 包的
`assets/`；素材不复制到 `knowledge/business/<频道>/`，也不堆在 `knowledge/work/`。content 提交 reviewing 后，gm 记录 owner
决定；只有 hash 仍有效的 approved 渠道稿才能 scheduled。首次排期把 `planned_at` 与 IANA
`timezone` 分开记录；scheduled 状态再次排期必须带原因并追加 reschedule event。发布前取消
必须带原因，记录保留为 cancelled，不删除 publication package。

owner 完成外部发布后，gm 用 `--to published` 记录实际发布时间与 URL。只有 scheduled
publication 可以确认发布；`schedule.planned_at` 保留为计划事实，实际事实写入独立的
`publication` 对象，并由 publish event 留痕。published 不能退回发布前状态，同一内容的再次
发布必须创建新的 publication。

growth 把指标定义维护在 `knowledge/business/growth/指标.md` 的 frontmatter：每个 metric
声明 key、label、unit、aggregation、scope 与适用 channels。观测值不写入定义：
publication 指标通过 `record-metrics` 追加到该 publication package 的 `指标.md`，同一窗口
不可覆盖；账号级数据通过 `record-channel-snapshot` 追加到独立的
`knowledge/business/growth/渠道快照.md`，不会归属到单个 publication。未注册 key、scope 或
channel 不匹配、缺失来源、重复窗口都会被拒绝。频道视图的指标摘要区分 `缺失`、`不可得`
（`{"available": false, "reason": "..."}`）与数值 `0`。

发布后 growth 用 `--to reviewed` 完成复盘：带 `--conclusion`（continue / iterate / stop /
inconclusive）与 `--next-action`，并引用创建时用 `--required-window` 声明的必需指标窗口；
必需窗口缺失就不能进入 reviewed。数据确实不可得时由 gm 带 `--exception-reason` 记录例外，
例外写入 review 与事件链。内容关闭由 gm 用 `--to closed` 完成：所有必需 publication 必须
已 reviewed 或已带原因 cancelled，否则失败并列出阻塞项；`--optional` 的 publication 不阻塞
关闭。选题作废由 gm 用 `--to cancelled --note "<原因>"` 完成：只对 proposed 或 drafting 内容
开放，取消是终态，内容卡保留取消原因与事件。阻塞不是状态：content 或 gm 用
`block <content_id> --reason "<原因>"` 把卡点记在内容卡上，条件解除后用
`unblock <content_id>` 解除，看板会把受阻内容单独标出。阻塞是硬闸门：受阻内容不能继续
写稿、请求审核、审批、创建 publication 或排期，先解除阻塞或作废再继续；已发布的事实、
指标与复盘不受影响。gm 记录的阻塞只有 gm 能解除。复盘与关闭只刷新 generated 视图，
不改写历史指标快照。

`build` 完整校验所有内容卡与 publication 卡后，原子替换 `knowledge/business/选题日历.md`
和各启用频道的 `发布记录.md`。日历分两节：没有目标日期的活跃内容进「待排期选题」，
有目标日期的进「已排期内容」；已关闭与已取消的内容是历史，不进日历。频道记录只显示 metadata
与 canonical links，不复制主稿、渠道稿、审批说明或资产。generated views 均标有
`GENERATED FILE — READ ONLY`，不得手工维护；生成失败会保留上一份有效视图。已有目标若
不是生成文件（缺 generated 标记），`build` 会拒绝覆盖并报错——旧格式需要人工确认，不能
被静默冲掉。

`build` 同时写出 `knowledge/business/dashboard.json`：看板的**只读契约**，把内容、
publication、任务、审批、阻塞、指标摘要与复盘结论编译成一份带版本号的 JSON，只含看板
需要的 metadata，不含主稿、渠道稿正文、复盘正文或资产内容。契约要点：

- `contract_version` 固定为 `1`；`read_only` 与 `generated` 标出它的性质
- `as_of` 取所有记录时间的最大值，不读系统时钟——同一份数据多次 build 结果完全一致
- `contents[]`、`publications[]`、`tasks[]`、`approvals[]`、`channels[]`、`team[]` 是
  看板要展示的条目；每条都带 `source_path` / `draft_path`，点击就能打开 canonical 源文件
- `scope` 是默认视图范围：未关闭或受阻内容、待审批、开放任务，以及未完成指标/复盘或
  近期发布/计划的 publication
- `diagnostics` 带校验的 errors 与 warnings：error 会保留上一份有效缓存并让 build 返回
  非零，warning 不阻止生成
- 任一 error 都不会产生半份 JSON：先全量校验，再原子替换；内容没变就跳过写入

## 发布前自检：tools/preflight

`tools/preflight <稿件路径>` 在发布前核对 canonical 稿件与品牌口径。稿件可以按位置指定，
也可以按稳定 ID 定位：

```sh
tools/preflight knowledge/content/<content_id>/主稿.md
tools/preflight knowledge/content/<content_id>/publications/<publication_id>/渠道稿.md
tools/preflight --content <content_id>
tools/preflight --publication <publication_id>
```

它只读 canonical 记录：

- 内容卡存在且 `content_id` 与目录一致；publication 卡存在且归属正确、渠道有效
- 稿件审批是 approved，且 SHA-256 仍覆盖当前稿件（审批后改稿会报「审批失效」）
- 渠道稿声明的渠道与发布卡一致；主稿与品牌口径的主渠道一致
- 没有命中 `品牌口径.md` 的禁用表述、术语表「不说什么」、作者人设的第一人称禁忌
- 字数在渠道口径区间内；CTA 话术与渠道口径一致（必含话术 / 禁写词）
- 内容卡声明 `pillar` 时核对内容支柱；未声明只警告
- 退出码：`0` 无硬性失败，`1` 有失败，`2` 用法错误

选题日历是 generated 只读视图，preflight 不读它；旧的 `knowledge/business/<channel>/`
稿件布局也不再支持，遇到时会明确指向 canonical 位置。稿件、内容卡与发布卡都会拒绝
symlink 和越出实例目录的真实路径；cancelled publication 不会被当作可发布。

**规则不在脚本里**：口径改 `品牌口径.md`；内容与 publication 事实改对应 canonical 记录。
只有新增「代码类」检查才需要改 `tools/preflight`——那是 owner 的活。

它是**内容线专用**工具。如果这个实例不做内容，把 `tools/preflight` 与 `tools/tests/`
连同 `opc-install.sh` 里两条 `Bash(./tools/preflight:*)` 白名单一起删掉即可，其余角色
不受影响。

## 窗口布局与多 pane

`layouts/` 下的 JSON 是 **herdr-app 的窗口布局**（不是 `hc` 的概念）。安装时按文件名装进
`~/.config/herdr-app/layouts/`：

| 文件 | 装成 | 用途 |
|---|---|---|
| `opc.json` | `<前缀>.json` | 默认：左侧栏 + 标签栏 + 右侧文件面板 |
| `focus.json` | `<前缀>-focus.json` | 只留主区，pane 占满整个窗口 |
| `grid.json` | `<前缀>-grid.json` | 更紧凑的 pane 边框与间距，适合 2×2 |
| `monitor.json` | `<前缀>-monitor.json` | 保留 agents 列表，去掉右侧面板 |
| `opc-dashboard.json` | `<前缀>-opc-dashboard.json` | 业务看板：只读面板，不含终端 |

切换：`ctrl-shift-l` 循环，或

```sh
herdr-app do layout.switch '{"name":"opc-grid"}'
```

### 业务看板：mods/opc-dashboard

看板是独立的 **herdr mod**（`mods/opc-dashboard/`），装进
`~/.config/herdr-app/mods/<前缀>-opc-dashboard/`。它只读 `knowledge/business/dashboard.json`，
不遍历也不解析 canonical Markdown，也不提供任何业务写入操作：canonical 记录的写入仍然
只有 workflow 命令，看板最多重跑一次 `build` 刷新 generated 视图：

- 顶部是数据截止时间、条目计数、刷新按钮，以及校验 warning / error 与缓存过期的提示
- 筛选支持时间、渠道、内容状态、publication 状态、角色、优先级与阻塞；「含历史」默认关闭，
  免得 closed / archived 的旧数据污染默认 KPI
- 分区展示紧急项、内容流水线、发布节奏、待 owner / gm 处理、渠道增长与复盘；终端与
  agent 状态只是辅助信息
- 点条目在上方读出对应 canonical 源文件（只读预览）；点角色名按 `knowledge/team.md` 的
  **准确终端名**找到那个终端，切回本实例的主布局并聚焦它，不按命名规则猜地址；
  打不开时给出可恢复的错误，不改业务状态

文件变化经过短 debounce 后刷新（连续事件合并成一次），另有低频兜底刷新与手动刷新。
安装器也会把 `mods/opc-dashboard` 装进 herdr 配置目录；没装 herdr 时只是少一个面板，
第一阶段的 workflow 与 generated Markdown 不受影响。

**一屏看多个角色**：

```sh
scripts/opc-panes.sh              # 默认铺当前启用的角色（最多 4 个）
scripts/opc-panes.sh gm dev       # 只铺指定的两个
```

它新开一个 tab，每个 pane 里跑 `hc attach <角色终端>`，看到的是该角色的实时画面；
按 `ctrl+\` 脱离后回到普通 shell。

**pane 的排列是运行时状态，布局文件无法预定义。** 布局只决定侧栏、标签栏、面板和
pane 边框，具体几格由 `pane.split` 决定——`opc-panes.sh` 负责这一步。

## 协作方式：文件为主，消息只做通知

1. 发起方把任务**追加**到 `knowledge/inbox/<角色>.md`，一行一条；条目带稳定
   `任务 ID`、`业务引用` 与验收标准。`knowledge/inbox/` 只有 gm 可写
2. 然后 `hc send <前缀>-<角色> "任务已投递：见 ..."` 喊一声
3. 对方读 inbox 执行；非 canonical 过程写进 `knowledge/work/<角色>/`。内容主稿通过
   `opc-workflow transition` 在固定内容包内进入 drafting / reviewing，gm 把 owner 决定落到
   内容卡；不靠 `git mv` 或复制主稿表达状态

**inbox 是队列，`decisions/` 是日志。** 角色只执行 inbox 里行首既无
`✅` 也无 `⛔` 的条目；状态变更必须写回派工条目，不能只写进决策文档。这条规则来自
一次真实事故：撤销只写在决策文档里，重启后的两个角色各自从旧日志把任务捞回来执行。

## 权限模型

每个 claude 角色带一份 `.opc/settings-<角色>.json`，通过 `--settings` 加载：

- **技能逐个批准**：白名单里只放**精确**的 `Skill(<名字>)` 规则，名字来自 `roles.json`
  里该角色的 `approvedSkills`。不放行裸 `Skill`——技能 frontmatter 里的
  `allowed-tools` 会在调用那一轮临时预授权工具，裸 `Skill` 等于把角色的工具面
  交给任意一个技能。`bypassPermissions` 下 allow 规则本就失效，技能照样能调，
  但那种模式下 deny 规则是唯一还在拦的东西（见下）
- 放行 `hc send` / `hc read` / `hc wait`，**只限本实例前缀**（`Bash(hc send opc-*)`），
  不跨实例操作终端；名字带引号时不匹配，退回人工批准（fail-closed）。**必须用终端名**
  （`hc read opc-content`），不能用 `hc ls` 里的地址（`t43`）——地址是本机全局的，
  没法按前缀限定，放行地址形式等于允许跨实例读终端
- 放行一组只读命令（`ls` / `cat` / `grep` / `jq` / `cd` 等），避免每个角色
  查文件都弹审批。**不含** `cp` / `mv` / `sed` / `tee` 等可写命令——它们能绕过下面的
  Edit 子树隔离；也**不含** `find` / `rg` / `sort` / `tree` / `echo` / `uniq` / `file`
  ——它们的参数（`find -exec`、`rg --pre`、`sort -o`、`tree -o`、`echo >`、
  `uniq <in> <out>`、`file -C`）能写文件或执行任意程序
- shell 循环（`for` / `while`）不放行：Claude Code 预检无法静态确认循环体，加规则也
  放不过；角色查文件用单条命令
- **能力缺口走上只读包装器**，不给原命令开口子：现有 `Bash(./tools/preflight:*)`；
  `sips` / `file` 这类能写文件又常用的命令不整条放行，改由包装器只暴露只读面
  （模式：只收路径、内部固定参数、不透传任何用户参数）。包装器一旦能透传
  `-s format` / `--out` / `-Z`，白名单就废了
- 放行写入 `Edit(./<自己子树>/**)`；`scope` 里写具体文件时生成精确路径
  `Edit(./knowledge/business/品牌口径.md)`，不拼 `/**`。路径是 cwd 相对，分发到任何目录都成立
- `knowledge/business/<频道>/` 只有 gm 能写；角色只写 `knowledge/work/<角色>/`
  和 `scope` 里列出的常驻表
- `scripts/` 与 `tools/` 都不在任何角色的 `scope` 内：两者都是执行面，只能由人改。
  被白名单放行的文件如果角色还能改写，白名单就形同虚设——改文件等于拿到它的全部权限。
  dev 的工具提案写在 `knowledge/work/dev/tools/`，owner 审过再搬进 `tools/`
- `git` / `rm` / `sudo` / `hc keys` 整类进 `deny`，任何模式都挡——前缀匹配绕得过变体
  （`git -C`、`rm -fr`），所以按命令整类封。`hc keys` 必须封：角色能用它替自己按掉
  审批框（按「1. Yes」），等于权限体系自废。**deny 规则在 `bypassPermissions` 下
  依然生效**（官方原文：Deny rules block in every mode），是那种模式下唯一的闸门
- 凭据路径进 `deny`：`Read(~/.ssh/**)`、`Read(~/.aws/**)`、`Read(~/.gnupg/**)`、
  `Read(~/.config/gh/**)`、`Read(~/.netrc)`、`Read(~/.npmrc)`
- **`permissions.blockWritesOutsideWorkingDirectories: true`**：文件工具在任何权限
  模式下都拒绝写工作目录之外的路径（`bypassPermissions` 也不例外）。角色的
  「只在实例里操作」由这条兜底，不靠 allow 规则——bypass 下 allow 无效。
  注意它**不限制 shell 命令**：`bash` 里 `rm` 仍能写任意路径，拦它靠 deny 规则
- **重启 / 停止团队**的操作进 `permissions.ask`（18 条规则，逐次弹审批等 owner 点头）：
  `scripts/opc-up.sh`、`scripts/opc-down.sh`（含 `bash` / `sh` / `./` / 绝对路径四种写法）、
  `hc kill`、`hc server stop`、`hc server restart`、`herdr-app do terminal.kill`，
  以及能伪造 TTY 的 `script` / `expect` / `socat` / `unbuffer`
- **脚本层还有一道独立门槛**：`opc-up.sh` / `opc-down.sh` 要求非 TTY 调用（agent、管道、
  CI）必须显式带 `--yes`，否则打印说明并 `exit 2`；owner 在自己终端手动跑（TTY）不受影响。
  权限层管「要不要人点头」，脚本层管「非交互调用不许自启自停」，两层互不依赖
- `--dry-run` 无副作用（只打印判定，不建 space、不起终端、不 `hc kill`），**不受脚本门槛
  限制**，任何时候都能用来验收；它会同时告诉你「去掉 `--dry-run` 会被放行还是被拒绝」
- **复合命令会被逐段判定**：`cmd; echo "exit=$?"` 里 `cmd` 命中白名单放行，`echo`
  命中不了就弹一次审批——看着像「权限没生效」，其实是命令写法的锅。`echo` 不放行
  （`echo > file` 能写文件，会绕过 Edit 子树隔离）；一条命令只做一件事即可消除这类噪音
- 启动与拦截都会写 `.opc/restart.log`（时间、TTY 与否、是否带 `--yes`、session id、cwd），
  下次再问「谁重启了团队」，直接查日志

> 为什么必须有白名单：不配时，agent 执行 `hc send` 会触发 Bash 审批并进入 `blocked`，
> 而 `hc send` 对 `blocked` 终端会拒绝投递——整个通知协议当场死锁。

### 权限模式

`roles.json` 里每个角色一个 `permissionMode`。OPC 只定义语义，各 CLI 用自己的参数
表达（口径在 `scripts/lib.sh`，安装器、名册、状态脚本共用一份）：

| 语义 | claude | codex | 还剩什么在拦 |
|---|---|---|---|
| `default` / `manual` | `--permission-mode default` | `--sandbox workspace-write --ask-for-approval on-request` | allow + ask + deny 全部照常 |
| `acceptEdits` | `--permission-mode acceptEdits` | 同 `default` | 文件编辑自动放行，Bash 仍要批 |
| `auto` | `--permission-mode auto` | `--approve-for-me --sandbox workspace-write` | 未命中规则的交给模型分类器判定 |
| `plan` | `--permission-mode plan` | `--sandbox read-only --ask-for-approval on-request` | 只读探查 |
| `dontAsk` | `--permission-mode dontAsk` | `--sandbox workspace-write --ask-for-approval never` | 只剩 allow / deny，不弹窗 |
| `bypassPermissions` | `--permission-mode bypassPermissions` | `--dangerously-bypass-approvals-and-sandbox` | **只剩 deny 规则 + 目录封锁 + CLI 自己的保护路径** |

其他 CLI 不接管：OPC 不认识它的审批语义，就不替它猜，按该 CLI 自己的默认跑，
装完会提示「以下角色的权限不由 OPC 托管」。

**模版默认 `bypassPermissions`**（`roles.json` 四个角色都是）。理由与代价：

- 没有弹窗，角色不会卡在 `blocked`；分类器不可用时也不会全队停摆
- **代价一**：allow 规则全部失效。角色的「只能写自己子树」不再由白名单保证，
  只剩规约里的行为约束
- **代价二**：官方定位是「只在容器 / VM 这类隔离环境里用」（*"Only use this mode in
  isolated environments like containers or VMs"*）。本机直接开，角色能删改实例
  之外的文件、能读写你的凭据目录
- **代价三**：shell 不受目录封锁约束。`blockWritesOutsideWorkingDirectories` 只管
  文件工具，`bash` 里的 `rm` / `curl` 仍能写任意路径

因此 bypass 模式下真正生效的只有三层，全部保留：

1. `deny` 规则（`git` / `rm` / `sudo` / `hc keys` + 凭据路径）——**所有模式都拦**
2. `blockWritesOutsideWorkingDirectories`——文件工具写不出工作目录
3. Claude Code 自己的保护路径（`.git` / `.claude`）

要更严就把某个角色改回 `dontAsk`：语义是「不弹窗，未预先放行的一律拒绝」，
allow 规则重新生效，作用域与只读白名单都回到白名单说了算。代价是白名单没覆盖的
动作会直接失败——角色会 `hc send` 报「权限缺口」，owner 补 `readonly_rules` 后
重跑安装、重启受影响角色。

> `bypassPermissions` 首次交互启动会弹一次风险确认（owner 本人在终端确认，
> 不要 agent 代按）；确认结果记在 `~/.claude/settings.json` 的
> `skipDangerousModePermissionPrompt`，之后不再弹。以 root / sudo 启动会被
> Claude Code 直接拒绝。

### 新增能力的三条路径

| 要加的东西 | 谁做 | 生效方式 |
|---|---|---|
| 只读命令 | owner 改 `opc-install.sh` 的 `readonly_rules` | 重跑安装 + 重启角色 |
| 新工具 `tools/<名字>` | dev 在 `knowledge/work/dev/tools/` 写提案，owner 审过搬进 `tools/` 并加 `Bash(./tools/<名字>:*)` | 重跑安装 + 重启角色 |
| 新角色 | `scripts/opc-role.sh add` | 新角色默认 `bypassPermissions`（与模版一致），scope 要自己填 |
| 新频道 | 改 `channels.json` | 重跑安装 |

**永远不要**通配放行 `Bash(./tools/*)`：那是一次性把所有工具（包括将来放进来的）
的执行权都签发出去。

## 不同 CLI 的能力差异

`roles.json` 的 `cli` 字段决定角色用哪个 agent 跑。不同 CLI 的「技能在哪」和
「谁来批」不是一回事，OPC 不把 Claude 的规则套给别的 CLI：

| CLI | 技能来源 | 权限模型 | OPC 是否托管 |
|---|---|---|---|
| `claude` | `.claude/skills/`、`~/.claude/skills/`、插件 skills/ | `settings.json` 的 allow/ask/deny + `--permission-mode`；Skill 调用需 allow 里有精确的 `Skill(<名字>)` | ✅ 生成 `.opc/settings-<角色>.json` |
| `codex` | `.agents/skills/`、`~/.agents/skills/`、`/etc/codex/skills/` | `--sandbox` / `--ask-for-approval` / `--approve-for-me` / `--dangerously-bypass-approvals-and-sandbox`；没有 Skill 工具权限 | ❌ 只映射参数 |
| 其他 | 由该 CLI 自行决定 | OPC 不接管 | ❌ 不生成设置 |

Codex 角色的 `permissionMode` 会被翻译成它自己的语义（表见「权限模式」一节）：
`dontAsk` → `--sandbox workspace-write --ask-for-approval never`，`default` /
`manual` / `acceptEdits` → `on-request`，`auto` → `--approve-for-me`，
`plan` → `--sandbox read-only`，`bypassPermissions` →
`--dangerously-bypass-approvals-and-sandbox`。

OPC **不为 codex 生成项目级权限 hook 或角色 scope 守卫**。模版只把每个角色在
`roles.json.permissionMode` 里的选择翻译成该 CLI 的原生启动参数；owner 可逐角色调整，
也可以用 CLI 自己的用户级配置继续收紧。`scope` 是协作边界与文档约定，不冒充身份认证
或 OS 级安全边界。

装完看 `knowledge/team.md` 的「CLI 能力差异」小节，那里按角色列明来源与模型；
`scripts/opc-status.sh` 也会打印同一份信息。

**跨 CLI 共享技能**：同一个技能要同时供 claude 与 codex 角色使用，需要放两份——
`~/.claude/skills/<名字>/` 与 `~/.agents/skills/<名字>/`。项目内技能同理，
`.claude/skills/` 与 `.agents/skills/` 互不相通。

## 多实例

前缀默认取目录名（slug 化），模板名、终端名、Herdr space 名都带前缀，互不冲突。
实例路径**不要含空格**，否则 hc 模板的 `command` 会被拆开。

一个模版可以开多个实例，每个实例有自己的前缀、自己的业务仓库、自己的
`.opc/instance.json`（记着模版来源）。同步是**单向**的：模版 → 实例。
实例之间互不影响——权限白名单按前缀限定，一个实例读不到另一个实例的终端。

## 排障

| 现象 | 处理 |
|---|---|
| `Executable not found in $PATH: "node"` | 重跑 `opc-install.sh` 生成启动器（走登录 shell 加载 mise） |
| agent 命令被**直接拒绝**（不弹窗） | `dontAsk` 的正常表现：该命令不在白名单。角色应 `hc send <前缀>-gm` 报「权限缺口」，owner 改 `scripts/opc-install.sh` 后重跑安装 |
| 角色调不动 Skill（`Permission to use Skill has been denied`） | `dontAsk` 下未放行的 Skill 直接被拒。白名单只放行精确的 `Skill(<名字>)`：把技能名加进 `roles.json` 里该角色的 `approvedSkills`，重跑 `scripts/opc-install.sh` 再重启角色。`bypassPermissions` 下 allow 规则不生效，技能本来就能调。另见：codex 角色没有 Skill 工具权限，技能只在 `.agents/skills/` 下被发现 |
| 角色能改实例之外的文件 | 检查 `.opc/settings-<角色>.json` 的 `permissions.blockWritesOutsideWorkingDirectories` 是否为 `true`。shell 里的写入不受它约束，靠 `deny` 规则拦 |
| agent 卡在 `blocked` | 只在 `default` / `manual` 模式下出现；查 `.opc/settings-*.json` 与 `roles.json` 的 `permissionMode` |
| 跑完命令后弹审批，像「权限没生效」 | 多半是命令尾巴上挂了第二段（`cmd; echo "exit=$?"`）——复合命令逐段判定，`echo` 不在白名单。改成一条命令只做一件事 |
| 角色读队友屏幕时弹审批 | 用了 `hc ls` 里的地址（`hc read t43`）；白名单只放行终端名，改成 `hc read opc-content` |
| 角色需要一条白名单外的命令 | 提需求做只读包装器，不要放行原命令；`sips` / `file` 这类能写文件的最典型 |
| 加了新工具却跑不起来 | 工具在 `tools/` 不等于可执行；要 owner 在 `readonly_rules` 加 `Bash(./tools/<名字>:*)` 再重跑安装。**不要**通配放行 `tools/*` |
| 停在「Do you trust this folder?」 | 信任确认是安全闸门，脚本不代按；在该 tab 手动确认，或 `hc keys <终端名> down enter` |
| `hc run` 报名字被占用 | 同前缀已有实例在跑，`hc ls` 查看或换前缀 |
| `opc-up` 报「模板或启动器缺失」 | 先跑 `opc-install.sh`，或 `opc-up.sh --install` |
| agent 执行 `opc-up.sh` / `opc-down.sh` 被拒 | 预期行为：非 TTY 且没带 `--yes` 会被脚本门槛 `exit 2`；owner 明确同意后加 `--yes` |
| 在模版仓库里跑 `opc-install.sh` 被拒 | 预期行为：模版不承载业务。用 `scripts/opc-new.sh <实例目录> <前缀>` 开实例 |
| `opc-lint.sh` 报「模版里出现 knowledge/ 下的文件」 | 有人把业务写进了模版仓库。把它挪回实例仓库，并删掉模版里那份 |
| `opc-lint.sh` 报「种子没有占位了」 | 种子被填成了真实内容。恢复成占位骨架，真实内容放实例 |
| `opc-sync.sh check` 报 `local-modified` | 实例本地改过、模版没动。要么提交本地改动，要么 `opc-sync.sh mark <路径>` 固化 |
| `opc-sync.sh check` 报 `unknown` | 没有基线快照，判不出本地是否改过。跑 `opc-sync.sh baseline --from <模版>` 固化基线后重跑 check |
| `opc-sync.sh pull` 退出码 3（冲突） | 本地与模版都改了同一文件。业务文件**没被改动**；合并结果在 `.opc/sync-conflicts/`，手改后重跑 |
| `opc-sync.sh pull` 说「将被覆盖的路径有未提交改动」 | 先提交或 stash 那些路径，或加 `--force` |
| 同步后角色行为没变 | `agents/` 与 `AGENTS.md` 是提示词，改动要重启才生效：`scripts/opc-down.sh && scripts/opc-up.sh` |
| `bash` 报 `xxx: unbound variable` 且变量后面跟着中文 | bash 会把中文全角字符吸进变量名。写成 `${xxx}` 再接中文 |

## License

MIT
