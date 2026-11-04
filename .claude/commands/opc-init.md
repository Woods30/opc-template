---
description: 初始化当前目录为 OPC 实例：检查依赖、选择角色与 CLI、生成配置
argument-hint: "[项目前缀]"
allowed-tools: Bash(scripts/opc-install.sh:*), Bash(scripts/opc-role.sh:*), Bash(scripts/opc-status.sh:*), Bash(jq:*), Bash(command -v:*), Read, Edit
---

# 初始化 OPC 实例

把当前目录初始化为一个 OPC 实例。**先问清楚，再动手装**——不要一上来就跑脚本。

## 1. 检查依赖

逐个检查 `hc`、`herdr-app`、`claude`、`jq`：

```sh
command -v hc herdr-app claude jq
```

缺任何一个，告诉用户缺什么、怎么装，然后**停止**，不要继续后面的步骤。

## 2. 读现有配置

读 `roles.json`，把角色用表格列给用户：名字、是否启用、CLI。

如果 `.opc/` 已经存在，说明这个目录初始化过。问用户是要**重新安装**（会覆盖
`.opc/` 与 `knowledge/team.md`，不动 `knowledge/` 业务内容）还是取消。

## 3. 问四件事

一次问一个，等回答再问下一个：

1. **项目前缀**：默认取目录名的小写 slug（`OPC` → `opc`）。前缀决定终端名与模板名。
2. **启用哪些角色**：默认 `roles.json` 里现有的全部。
3. **每个角色用哪个 CLI**：默认 `claude`。
4. **内容频道清单**：默认 `channels.json` 里现有的；没有文件时问用户要哪几个频道
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
scripts/opc-install.sh <前缀>
```

失败就把错误原样贴给用户，不要自己改脚本绕过。

## 6. 跑一次初始化测试（接真实任务之前）

模板调试完成前**不接真实业务任务**，先跑一次端到端测试，确认链路通：

1. gm 向 content 派测试任务：追加到 `knowledge/inbox/content.md` 并
   `hc send <前缀>-content`——「在 `knowledge/work/content/测试-<YYYY-MM-DD>.md`
   写 100 字以内的占位文本，标注『测试稿，不发布』，完成后回报」。
2. content 写文件，`hc send <前缀>-gm "完成：knowledge/work/content/测试-<YYYY-MM-DD>.md"`。
3. gm 收到后，在 `knowledge/daily/<YYYY-MM-DD>.md` 记一行「初始化测试：通过」或
   「初始化测试：卡在 <环节>」。

验收：三步都成功，且**全程没有审批弹窗**。测试稿留在 `work/`，不进 `business/`——
它只是验证链路，不是产出。任何一步卡住，先修配置，不要带着问题接真实任务。

## 7. 报告并询问启动

运行 `scripts/opc-status.sh`，把输出给用户看。然后问是否现在启动团队。

**启动团队属于破坏性操作**：会清空所有角色已有的会话上下文，必须由 owner 逐次明确
同意。规则：

- 不得为了「验证配置是否生效」「刷新权限」而重启团队；
- owner 同意后，**由 owner 在自己的终端执行** `scripts/opc-up.sh`，agent 不代为执行；
- 本 skill 不得批量重启、不得把重启当作安装后的自动步骤。

## 边界

- 不改 `knowledge/` 下的业务内容。
- 不替用户决定启用哪些角色。
- 不跳过依赖检查，不跳过提问直接安装。
- 首次启动若停在「Do you trust this folder?」，提示用户在该 tab 手动确认，
  不要用 `hc keys` 代按。
