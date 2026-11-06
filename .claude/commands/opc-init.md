---
description: 初始化当前目录为 OPC 实例：检查依赖、选择角色与 CLI、生成配置
argument-hint: "[项目前缀]"
allowed-tools: Bash(scripts/opc-install.sh:*), Bash(scripts/opc-role.sh:*), Bash(scripts/opc-status.sh:*), Bash(jq:*), Bash(command -v:*), Read, Edit
---

# 初始化 OPC 实例

把当前目录初始化为一个 OPC 实例。**先问清楚，再动手装**——不要一上来就跑脚本。

## 0. 先确认这里不是模版仓库

用 Read 读根目录的 `.opc-template-repo`。文件存在 → 这里是模版仓库，
**立即停止**：告诉用户「这里是模版仓库，不承载业务数据」，并给出开实例的命令
`scripts/opc-new.sh <实例目录> <前缀>`，然后结束本流程，不要继续后面的步骤。

文件不存在 → 继续第 1 步。

## 1. 检查依赖

逐个检查 `hc`、`herdr-app`、`claude`、`jq`：

```sh
command -v hc herdr-app claude jq
```

缺任何一个，告诉用户缺什么、怎么装，然后**停止**，不要继续后面的步骤。

`codex` 是可选依赖——用 `command -v codex` 探测即可，缺了不影响默认流程，
但要用 codex 角色就必须在。

## 2. 读现有配置

读 `roles.json`，把角色用表格列给用户：名字、是否启用、CLI。

如果 `.opc/` 已经存在，说明这个目录初始化过。问用户是要**重新安装**（会覆盖
`.opc/` 与 `knowledge/team.md`，不动 `knowledge/` 业务内容）还是取消。

## 3. 问五件事

一次问一个，等回答再问下一个：

1. **项目前缀**：默认取目录名的小写 slug（`OPC` → `opc`）。前缀决定终端名与模板名。
2. **启用哪些角色**：默认 `roles.json` 里现有的全部。
3. **每个角色用哪个 CLI**：只列本机实际装了的（`scripts/opc-install.sh` 的检测逻辑
   看 `command -v`，清单见 `scripts/lib.sh` 的 `opc_known_clis`）。默认 `claude`。
   **选 `codex` 前先说清差异**——两者的
   技能来源不同（claude 看 `.claude/skills/` 与 `~/.claude/skills/`，codex 看
   `.agents/skills/` 与 `~/.agents/skills/`），权限模型也不同（claude 由 OPC 生成
   `settings-<角色>.json`；codex 用 `--sandbox` / `--ask-for-approval` /
   `--approve-for-me` / `--dangerously-bypass-approvals-and-sandbox`，OPC 只做参数映射，
   不生成白名单）。同一个技能要两边都能用，得在两处各放一份。
4. **权限模式**：默认 `bypassPermissions`（模版默认）。选之前说清代价——该模式下
   **allow 规则不生效**，仍然拦得住的只有 deny 规则（`git`/`rm`/`sudo`/`hc keys`
   与凭据路径）、文件工具的工作目录写入封锁、CLI 自己的保护路径；官方定位是
   「只在容器 / VM 这类隔离环境里用」。想更严就选 `dontAsk`：不弹窗，未预先放行的
   一律拒绝，作用域与只读白名单重新说了算，代价是白名单没覆盖的动作会直接失败。
   选完把 `permissionMode` 写进 `roles.json`。
5. **内容频道清单**：默认 `channels.json` 里现有的；没有文件时问用户要哪几个频道
   （公众号 / X / 小红书 / 抖音 / 知乎 …）。每个频道要一个英文 id（小写 slug）和一个
   中文显示名；暂不做的频道写 `enabled: false`。

## 4. 改配置

按回答用 Edit 修改 `roles.json` 的 `enabled` 与 `cli` 字段、`channels.json` 的
`enabled` 与 `name` 字段。**不要**用 shell 重定向改 JSON。新增角色请改用
`scripts/opc-role.sh add`，不要手写条目。

`channels.json` 的 `id` 必须匹配 `^[a-z][a-z0-9-]{0,19}$`——它会直接成为
`knowledge/business/<id>/` 的目录名。

## 5. 安装

```sh
scripts/opc-install.sh --no-input <前缀>
```

这里的角色与 CLI 已经在第 3 步问过了，所以用 `--no-input` 免得再问一遍。
失败就把错误原样贴给用户，不要自己改脚本绕过。

## 6. 跑一次初始化测试（接真实任务之前）

模板调试完成前**不接真实业务任务**，先跑一次端到端测试，确认链路通：

1. gm 向 content 派测试任务：追加到 `knowledge/inbox/content.md` 并
   `hc send <前缀>-content`——「在 `knowledge/work/content/测试-<YYYY-MM-DD>.md`
   写 100 字以内的占位文本，标注『测试稿，不发布』，完成后回报」。
2. content 写文件，`hc send <前缀>-gm "完成：knowledge/work/content/测试-<YYYY-MM-DD>.md"`。
3. gm 收到后，在 `knowledge/decisions/<YYYY-MM-DD>-初始化测试.md` 记一行
   「初始化测试：通过」或「初始化测试：卡在 <环节>」。

验收：三步都成功，且**全程没有审批弹窗**。测试稿留在 `work/`，不进 `business/`——
它只是验证链路，不是产出。任何一步卡住，先修配置，不要带着问题接真实任务。

## 7. 报告并询问启动

运行 `scripts/opc-status.sh`，把输出给用户看。然后问是否现在启动团队。

**启动团队属于破坏性操作**：会清空所有角色已有的会话上下文，必须由 owner 逐次明确
同意。规则：

- 不得为了「验证配置是否生效」「刷新权限」而重启团队；
- owner 同意后，**由 owner 在自己的终端执行** `scripts/opc-up.sh`，agent 不代为执行；
- 本 skill 不得批量重启、不得把重启当作安装后的自动步骤。

**`bypassPermissions` 首次启动会弹一次风险确认**：owner 要在自己终端里手动确认，
agent 不得代按（`hc keys` 也在 deny 清单里，代按不了）。确认结果记在
`~/.claude/settings.json`，之后不再弹。

## 边界

- 不改 `knowledge/` 下的业务内容。
- 不替用户决定启用哪些角色。
- 不跳过依赖检查，不跳过提问直接安装。
- 首次启动若停在「Do you trust this folder?」，提示用户在该 tab 手动确认，
  不要用 `hc keys` 代按。
