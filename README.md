# OPC 工程模版

一套**一人公司（One Person Company）的 AI 团队脚手架**：把 gm / content / growth / dev
四个角色做成独立运行的 agent，用文件协作、用消息唤醒。

- 基于 [`herdr-core`](https://github.com/)（`hc`）的模板机制，每个角色一个持久终端
- 在 Herdr 窗口里各占一个 tab，随时可以看、可以接手
- 角色、CLI、可写目录全部由 `roles.json` 配置，可增删启停
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

scripts/opc-install.sh        # 生成模板、权限白名单、启动器
scripts/opc-up.sh             # 启动所有已启用角色
scripts/opc-status.sh         # 看状态
scripts/opc-down.sh           # 停止

scripts/opc-up.sh --install   # 模板/启动器缺失时先装再启动
```

`opc-up.sh` 默认 **fail-closed**：缺模板或启动器就报错退出，不自动执行安装脚本。
脚本属于执行面，agent 不可写（`scripts/` 不在任何角色的 `scope` 内），所以启动时
也不能悄悄把它跑起来。

也可以在 agent 里初始化：在该目录启动 Claude Code，输入 `/opc-init`。
它会检查依赖、问你前缀/角色/CLI，改好 `roles.json` 再跑安装。

## 一个实例长什么样

```
roles.json           角色注册表：启用/停用、CLI、可写子树
AGENTS.md            各角色共用的规约（Claude Code 自动加载）
CLAUDE.md            一行：@AGENTS.md
agents/              各角色的 hc 模板源（唯一事实来源）
knowledge/           唯一事实来源：inbox / decisions / content / growth / product / daily
scripts/             安装、启停、状态、角色管理
layouts/             Herdr 布局与预览图
.opc/                安装脚本生成（不进版本库）
```

## 角色是配置

默认四个角色只是初始值。`roles.json` 每条记录：

```json
{
  "name": "growth",
  "enabled": true,
  "cli": "claude",
  "template": "agents/opc-growth.md",
  "scope": ["knowledge/growth"]
}
```

| 字段 | 作用 |
|---|---|
| `enabled` | 停用后不生成模板、不启动、不进名册 |
| `cli` | 该角色用哪个 CLI，默认 `claude` |
| `scope` | 允许自动写入的子树，其余写入仍需人工批准 |
| `template` | 角色简报路径 |

用命令改：

```sh
scripts/opc-role.sh list
scripts/opc-role.sh disable growth
scripts/opc-role.sh enable growth
scripts/opc-role.sh add editor --desc "负责润色与事实核查" --scope knowledge/editor
scripts/opc-role.sh add reviewer --cli codex --desc "独立审稿" --scope knowledge/review
```

启动时也可以只挑一部分：`scripts/opc-up.sh gm content`。

## 协作方式：文件为主，消息只做通知

1. 发起方把任务**追加**到 `knowledge/inbox/<角色>.md`，一行一条
2. 然后 `hc send <前缀>-<角色> "任务已投递：见 ..."` 喊一声
3. 对方读 inbox 执行，产出写进 `knowledge/<领域>/`，回 `hc send` 报告路径

结论必须落盘。终端里的对话会消失，文件不会。

## 权限模型

每个 claude 角色带一份 `.opc/settings-<角色>.json`，通过 `--settings` 加载：

- 放行 `hc send` / `hc read` / `hc wait`，**只限本实例前缀**（`Bash(hc send opc-*)`），
  不跨实例操作终端；名字带引号时不匹配，退回人工批准（fail-closed）
- 放行写入 `Edit(./<自己子树>/**)`，路径是 cwd 相对，分发到任何目录都成立
- `scripts/` 不在任何角色的 `scope` 内：脚本决定权限边界，只能由人改
- `git` / `rm` / `sudo` 整类进 `deny`，任何模式都挡——前缀匹配绕得过变体
  （`git -C`、`rm -fr`），所以按命令整类封
- 模式固定 `default`；不用 `acceptEdits`（会架空子树隔离），不用 `bypassPermissions`

> 为什么必须有白名单：不配时，agent 执行 `hc send` 会触发 Bash 审批并进入 `blocked`，
> 而 `hc send` 对 `blocked` 终端会拒绝投递——整个通知协议当场死锁。

## 多实例

前缀默认取目录名（slug 化），模板名、终端名、Herdr space 名都带前缀，互不冲突。
实例路径**不要含空格**，否则 hc 模板的 `command` 会被拆开。

## 排障

| 现象 | 处理 |
|---|---|
| `Executable not found in $PATH: "node"` | 重跑 `opc-install.sh` 生成启动器（走登录 shell 加载 mise） |
| agent 卡在 `blocked` | 权限白名单没生效，查 `.opc/settings-*.json` |
| 停在「Do you trust this folder?」 | 信任确认是安全闸门，脚本不代按；在该 tab 手动确认，或 `hc keys <终端名> down enter` |
| `hc run` 报名字被占用 | 同前缀已有实例在跑，`hc ls` 查看或换前缀 |
| `opc-up` 报「模板或启动器缺失」 | 先跑 `opc-install.sh`，或 `opc-up.sh --install` |

## License

MIT
