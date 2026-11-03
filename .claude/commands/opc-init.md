---
description: 初始化当前目录为 OPC 实例：检查依赖、选择角色与 CLI、生成配置
argument-hint: "[项目前缀]"
allowed-tools: Bash(scripts/opc-install.sh:*), Bash(scripts/opc-role.sh:*), Bash(scripts/opc-status.sh:*), Bash(scripts/opc-up.sh:*), Bash(jq:*), Bash(command -v:*), Read, Edit
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

## 3. 问三件事

一次问一个，等回答再问下一个：

1. **项目前缀**：默认取目录名的小写 slug（`OPC` → `opc`）。前缀决定终端名与模板名。
2. **启用哪些角色**：默认 `roles.json` 里现有的全部。
3. **每个角色用哪个 CLI**：默认 `claude`。

## 4. 改配置

按回答用 Edit 修改 `roles.json` 的 `enabled` 与 `cli` 字段。**不要**用 shell 重定向
改 JSON。新增角色请改用 `scripts/opc-role.sh add`，不要手写条目。

## 5. 安装

```sh
scripts/opc-install.sh <前缀>
```

失败就把错误原样贴给用户，不要自己改脚本绕过。

## 6. 报告并询问启动

运行 `scripts/opc-status.sh`，把输出给用户看。然后问是否现在启动团队；用户同意
再运行 `scripts/opc-up.sh`。

## 边界

- 不改 `knowledge/` 下的业务内容。
- 不替用户决定启用哪些角色。
- 不跳过依赖检查，不跳过提问直接安装。
- 首次启动若停在「Do you trust this folder?」，提示用户在该 tab 手动确认，
  不要用 `hc keys` 代按。
