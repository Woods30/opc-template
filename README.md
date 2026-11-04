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

```sh
git clone <this-repo> ~/Documents/my-opc
cd ~/Documents/my-opc

scripts/opc-install.sh        # 生成模板、权限白名单、启动器、目录骨架
scripts/opc-up.sh             # 启动所有已启用角色
scripts/opc-status.sh         # 看状态
scripts/opc-down.sh           # 停止

scripts/opc-up.sh --install   # 模板/启动器缺失时先装再启动
```

`opc-up.sh` 默认 **fail-closed**：缺模板或启动器就报错退出，不自动执行安装脚本。
脚本属于执行面，agent 不可写（`scripts/` 不在任何角色的 `scope` 内），所以启动时
也不能悄悄把它跑起来。

**推荐路径**：在该目录启动 Claude Code，输入 `/opc-init`。它会检查依赖、问前缀/角色/
CLI/频道，改好 `roles.json` 与 `channels.json`，跑安装，并跑一次端到端测试任务。

## 一个实例长什么样

```
roles.json           角色注册表：启用/停用、CLI、可写子树、权限模式
channels.json        频道清单：id / 中文名 / 是否启用
AGENTS.md            各角色共用的规约（Claude Code 自动加载）
LESSONS.md           全局经验教训库（gm 维护；角色写各自的 work/<角色>/LESSONS.md）
CLAUDE.md            一行：@AGENTS.md
agents/              各角色的 hc 模板源（唯一事实来源）
knowledge/           唯一事实来源：
                     ├── business/  结果：频道成稿与物料、增长、产品、常驻口径
                     ├── work/      过程：每个角色一个子树（草稿、提案、日志）
                     ├── review/    待 owner 过审的对外发布内容
                     └── decisions/ daily/ inbox/
scripts/             安装、启停、状态、角色管理（执行面，仅 owner 可写）
tools/               只读包装器与校验工具（执行面，仅 owner 可写）
layouts/             Herdr 窗口布局（默认 / focus / grid / monitor）
.opc/                安装脚本生成（不进版本库）
```

**生成物不要手改**：`knowledge/team.md`、`knowledge/business/README.md`、
`knowledge/inbox/<角色>.md`（首次生成后由角色使用）、`.opc/**` 都由
`scripts/opc-install.sh` 生成。

**结果与过程分开**：老板日常只看 `knowledge/business/`；`knowledge/work/` 里的草稿
再多也不会干扰。命名规则：目录是结构用英文，文件是内容用中文。

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

## 发布前自检：tools/preflight

`tools/preflight <稿件路径>` 在发布前核对稿件与两份源文件是否一致：

- 稿件在 `选题日历.md` 里，登记的路径、主渠道与文件本身一致
- 没有命中 `品牌口径.md` 的禁用表述、术语表「不说什么」、作者人设的第一人称禁忌
- 字数在渠道口径区间内；CTA 话术与渠道口径一致（必含话术 / 禁写词）
- 退出码：`0` 无硬性失败，`1` 有失败，`2` 用法错误

**规则不在脚本里**：改口径改 `品牌口径.md`，改选题改 `选题日历.md`，脚本自动跟随。
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

切换：`ctrl-shift-l` 循环，或

```sh
herdr-app do layout.switch '{"name":"opc-grid"}'
```

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

1. 发起方把任务**追加**到 `knowledge/inbox/<角色>.md`，一行一条
2. 然后 `hc send <前缀>-<角色> "任务已投递：见 ..."` 喊一声
3. 对方读 inbox 执行，过程写进 `knowledge/work/<角色>/`，回 `hc send` 报告路径；
   gm 审过后用 `git mv` 搬进 `knowledge/business/`，对外发布内容先进 `knowledge/review/`

**inbox 是队列，`daily/` 与 `decisions/` 是日志。** 角色只执行 inbox 里行首既无
`✅` 也无 `⛔` 的条目；状态变更必须写回派工条目，不能只写进决策文档。这条规则来自
一次真实事故：撤销只写在决策文档里，重启后的两个角色各自从旧日志把任务捞回来执行。

## 权限模型

每个 claude 角色带一份 `.opc/settings-<角色>.json`，通过 `--settings` 加载：

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
  审批框（按「1. Yes」），等于权限体系自废
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

### 权限模式的推荐上线顺序

模版默认 `permissionMode: "default"`——新实例先看得见弹窗，才能知道白名单缺什么。

1. **`default` 跑通一轮**：初始化测试任务全程无弹窗，说明常用能力都在白名单里。
2. **切 `dontAsk`**：把 `roles.json` 四个角色改成 `"dontAsk"`，重跑安装，重启团队。
   语义是「不弹窗，未预先放行的一律拒绝」——不会把终端卡成 `blocked`。
3. **观察并补白名单**：角色遇到拒绝会 `hc send` 报「权限缺口」；owner 改
   `scripts/opc-install.sh` 的 `readonly_rules`，重跑安装，重启受影响角色。

**不建议 `auto`**：它把每条未命中规则的命令交给模型分类器判定，安全边界从「可审计」
变成「不可复现」，且依赖远端服务（分类器不可用时全队停摆）。`bypassPermissions`
会被安装脚本直接拒绝。

### 新增能力的三条路径

| 要加的东西 | 谁做 | 生效方式 |
|---|---|---|
| 只读命令 | owner 改 `opc-install.sh` 的 `readonly_rules` | 重跑安装 + 重启角色 |
| 新工具 `tools/<名字>` | dev 在 `knowledge/work/dev/tools/` 写提案，owner 审过搬进 `tools/` 并加 `Bash(./tools/<名字>:*)` | 重跑安装 + 重启角色 |
| 新角色 | `scripts/opc-role.sh add` | 新角色默认 `default`，跑通一轮后再切 `dontAsk` |
| 新频道 | 改 `channels.json` | 重跑安装 |

**永远不要**通配放行 `Bash(./tools/*)`：那是一次性把所有工具（包括将来放进来的）
的执行权都签发出去。

## 多实例

前缀默认取目录名（slug 化），模板名、终端名、Herdr space 名都带前缀，互不冲突。
实例路径**不要含空格**，否则 hc 模板的 `command` 会被拆开。

## 排障

| 现象 | 处理 |
|---|---|
| `Executable not found in $PATH: "node"` | 重跑 `opc-install.sh` 生成启动器（走登录 shell 加载 mise） |
| agent 命令被**直接拒绝**（不弹窗） | `dontAsk` 的正常表现：该命令不在白名单。角色应 `hc send <前缀>-gm` 报「权限缺口」，owner 改 `scripts/opc-install.sh` 后重跑安装 |
| agent 卡在 `blocked` | 只在 `default` / `manual` 模式下出现；查 `.opc/settings-*.json` 与 `roles.json` 的 `permissionMode` |
| 跑完命令后弹审批，像「权限没生效」 | 多半是命令尾巴上挂了第二段（`cmd; echo "exit=$?"`）——复合命令逐段判定，`echo` 不在白名单。改成一条命令只做一件事 |
| 角色读队友屏幕时弹审批 | 用了 `hc ls` 里的地址（`hc read t43`）；白名单只放行终端名，改成 `hc read opc-content` |
| 角色需要一条白名单外的命令 | 提需求做只读包装器，不要放行原命令；`sips` / `file` 这类能写文件的最典型 |
| 加了新工具却跑不起来 | 工具在 `tools/` 不等于可执行；要 owner 在 `readonly_rules` 加 `Bash(./tools/<名字>:*)` 再重跑安装。**不要**通配放行 `tools/*` |
| 停在「Do you trust this folder?」 | 信任确认是安全闸门，脚本不代按；在该 tab 手动确认，或 `hc keys <终端名> down enter` |
| `hc run` 报名字被占用 | 同前缀已有实例在跑，`hc ls` 查看或换前缀 |
| `opc-up` 报「模板或启动器缺失」 | 先跑 `opc-install.sh`，或 `opc-up.sh --install` |
| agent 执行 `opc-up.sh` / `opc-down.sh` 被拒 | 预期行为：非 TTY 且没带 `--yes` 会被脚本门槛 `exit 2`；owner 明确同意后加 `--yes` |

## License

MIT
