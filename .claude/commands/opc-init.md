---
description: 初始化一个 OPC 实例：检查依赖、选择目录/角色/CLI、调用 opc install
argument-hint: "[实例目录] [项目前缀]"
allowed-tools: Bash(bin/opc:*), Bash(opc:*), Bash(command -v:*), Bash(jq:*), Read, Write, Edit
---

# 初始化 OPC 实例

把用户指定的目录初始化成一个 OPC 实例。**先问清楚，再动手装**——不要一上来就跑命令。
实际的创建、复制、git 提交、全局 UI 安装都由 `bin/opc install` 完成，本流程只负责
问对问题并把答案传给它。

## 0. 找到 `opc` 入口

按顺序判断：

1. 当前目录或祖先目录有 `bin/opc` → 用这个开发副本（`<模版>/bin/opc`）；
2. `command -v opc` 有输出 → 用全局命令；
3. 都没有 → 告诉用户先 clone 模版并执行一次 `bin/opc install`，或把
   `~/.local/bin` 加进 PATH，然后**停止**。

确定后记下入口路径，后面统一用 `$OPC` 表示。

## 1. 检查依赖

逐个检查 `hc`、`herdr-app`、`claude`、`jq`：

```sh
command -v hc herdr-app claude jq
```

缺任何一个，告诉用户缺什么、怎么装，然后**停止**。
`codex` 是可选依赖——用 `command -v codex` 探测即可；要用 codex 角色就必须在。

## 2. 确认目标目录

- 当前目录**不是**模版仓库（没有 `.opc-template-repo`）且为空或不存在 →
  默认目标就是当前目录。
- 当前目录是模版仓库 → 目标必须由用户指定（不能把模版目录本身变成实例）。
- 目标非空：只有空目录、或只含 `.git` 的空仓库可以安装；否则让用户换目录或先清理。

问用户：

1. **实例目录**：默认取上面判断的结果。
2. **项目前缀**：默认取目录名的小写 slug（`OPC` → `opc`）。
   前缀决定终端名与模板名，必须匹配 `^[a-z0-9][a-z0-9_-]{0,30}$`。

## 3. 问角色、CLI、权限与频道

模版自带的 `template/roles.json` 是初始值。若目标目录已有 `roles.json`，先读它列给
用户；否则按模版默认值问。

一次问一组，等回答再继续：

1. **启用哪些角色**：默认全部启用。
2. **每个角色用哪个 CLI**：只列本机实际装了的（`claude` / `codex` / …）。默认 `claude`。
   **选 `codex` 前先说清差异**——技能来源不同（claude 看 `.claude/skills/` 与
   `~/.claude/skills/`，codex 看 `.agents/skills/` 与 `~/.agents/skills/`），权限模型
   也不同（claude 由 OPC 生成 `settings-<角色>.json`；codex 只做启动参数映射）。
3. **权限模式**：默认 `bypassPermissions`。选之前说清代价——该模式下 **allow 规则
   不生效**，仍然拦得住的只有 deny 规则（`git`/`rm`/`sudo`/`hc keys` 与凭据路径）、
   文件工具的工作目录写入封锁、CLI 自己的保护路径；官方定位是「只在容器 / VM
   这类隔离环境里用」。想更严就选 `dontAsk`：不弹窗，未预先放行的一律拒绝。
4. **内容频道清单**：默认沿用 `template/channels.json`（通常为空）。每个频道要一个
   英文 id（小写 slug）和一个中文显示名；暂不做的写 `enabled: false`。

## 4. 调用 install

把答案写成一个临时 JSON 文件（用 Write，不要用 shell 重定向），形如：

```json
{
  "prefix": "acme",
  "roles": {
    "gm": { "enabled": true, "cli": "claude", "permissionMode": "bypassPermissions" },
    "content": { "enabled": true, "cli": "claude" }
  },
  "channels": [
    { "id": "wechat", "name": "公众号", "enabled": true }
  ]
}
```

先跑 dry-run 给用户看：

```sh
"$OPC" install <实例目录> <前缀> --answers <临时文件> --dry-run
```

用户确认后正式执行：

```sh
"$OPC" install <实例目录> <前缀> --answers <临时文件>
```

- 安装器会跑 `scripts/opc-install.sh --no-input`，不会再提问。
- 失败就把错误原样贴给用户，不要自己改脚本绕过。
- 安装会创建全局 UI（布局 `opc`、mod `opc-tabs` / `opc-dashboard`）并写注册表；
  第一次还会把 `~/.local/bin/opc` 链到缓存副本。
- 清理第 4 步的临时 JSON。

## 5. 报告并询问启动

在实例目录运行 `scripts/opc-status.sh`，把输出给用户看。然后问是否现在启动团队。

**启动团队属于破坏性操作**：会清空所有角色已有的会话上下文，必须由 owner 逐次明确
同意。规则：

- 不得为了「验证配置是否生效」「刷新权限」而重启团队；
- owner 同意后，**由 owner 在自己的终端执行** `scripts/opc-up.sh`，agent 不代为执行；
- 本 skill 不得批量重启、不得把重启当作安装后的自动步骤。

**`bypassPermissions` 首次启动会弹一次风险确认**：owner 要在自己终端里手动确认，
agent 不得代按（`hc keys` 也在 deny 清单里，代按不了）。

## 边界

- 不在模版仓库里直接创建实例；目标目录不能是模版目录。
- 不改 `knowledge/` 下的业务内容。
- 不替用户决定启用哪些角色、用哪个 CLI。
- 不跳过依赖检查，不跳过提问直接安装。
- 首次启动若停在「Do you trust this folder?」，提示用户在该 tab 手动确认，
  不要用 `hc keys` 代按。
