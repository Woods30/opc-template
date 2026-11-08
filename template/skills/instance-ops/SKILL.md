---
name: instance-ops
description: 运行实例的日常操作：启停角色终端、查名册与状态、管频道、升级模版，以及出问题时去哪里查。
---

# 实例运维

这份技能只讲**怎么把实例跑起来、怎么找到该找的东西**。内容怎么写见 `knowledge-writing`，
内容生命周期怎么推见 `opc-workflow`。

## 启停团队

```sh
scripts/opc-up.sh [--install] [--yes] [--dry-run] [角色...]
scripts/opc-down.sh [--yes] [--dry-run] [角色...]
scripts/opc-panes.sh [角色...]
```

- 不带角色参数 = 处理 `roles.json` 里所有已启用角色。
- `--dry-run` 只打印门槛判定与将要处理的角色，不执行任何启动或停止动作。
- `--yes` 表示 owner 已知启动或停止会清空这些角色的会话上下文；非交互调用必须带。
- `--install` 表示模板或启动器缺失时先重跑安装脚本；默认**不**自动执行。
- `opc-up.sh` 需要 `herdr-app` 与 `hc` 在 PATH 里，缺了会直接报错退出。

`scripts/opc-panes.sh` 把角色铺成一屏多 pane，配合全局布局 `opc-grid` 用；它只是看画面，
不代替 `opc-up.sh`。

## 角色与终端

- `roles.json` 是角色的唯一事实源：启用状态、CLI、模型、权限模式、可写子树、选中的技能
  都在里面。
- 每个角色在自己那个 tab 里跑一个常驻会话。**当前实例的完整注册表在
  `knowledge/team.md`**，那是唯一权威来源——委派前先查注册表，不要凭记忆拼终端名。
- `hc ls` 列出的是**全部** live 终端，包括别的实例、别的项目空间，以及目录已被删掉却还挂着的
  残终端。名册之外的终端与本实例无关，不要读它们的屏幕。
- 跨终端读屏用终端名：`hc read <前缀>-<角色>`。地址形式（如 `t43`）不在白名单里，会退回报批。
- 角色增删启停：`scripts/opc-role.sh list | add <角色> | enable <角色> | disable <角色>`。
  改完会自动重跑安装脚本，模板、权限与名册同步更新。

## 查状态

```sh
scripts/opc-status.sh
```

一次看清每个角色是否启用、终端是否在跑、各自有多少张开放的任务卡。

## 频道

- 频道清单在 `channels.json`，只有 `enabled` 的频道参与流程。
- 频道目录 `knowledge/business/<频道>/` 只放 generated 发布记录，不放稿件或资产副本。
- 增删频道改 `channels.json` 后重跑 `scripts/opc-install.sh`，目录与只读视图随之刷新。

## 升级

- 升级由 owner 在模版仓库里执行：`bin/opc upgrade <实例目录>`（或 `bin/opc upgrade --all`）。
  **实例里没有升级脚本**，角色不要尝试升级。
- 升级会覆盖机制文件（`scripts/`、`tools/`），并按基线更新起始材料（根 `AGENTS.md`、
  `agents/`、`skills/`、业务 seeds）。业务内容 `knowledge/` 永远不被覆盖。
- 机制文件被本地改过时升级会拒绝，并打印 diff；确认改动不要了再由 owner 加
  `--force-mechanism` 覆盖。
- 改过或删掉的起始材料由 owner 保留，升级只提示不覆盖；技能目录按整目录冻结——
  改过任一文件就整个技能跳过更新。
- 升级后需要重跑一次实例安装器（`bin/opc upgrade` 会自动做），让 hc 模板、权限设置与
  技能索引同步更新。

## 权限缺口

角色默认跑在 `bypassPermissions`：没有弹窗，也没有 allow 规则兜底。仍然拦得住的只有
`deny` 规则、文件工具的工作目录写入封锁、CLI 自己的保护路径。

被拒时按顺序处理：先换写法（用已放行的只读命令或 `tools/` 里的包装器），换不了就
`hc send <前缀>-gm` 上报裁决请求，**不要硬扛、不要自己找绕过的命令**。任务卡由
`tools/opc-workflow` 的任务命令族维护，角色不要直接改它的完成态。

## 出问题时去哪里查

| 现象 | 去哪里看 |
|---|---|
| 角色没起来 / 终端找不到 | `scripts/opc-status.sh`、`knowledge/team.md`；`hc ls` 里名册之外的终端与本实例无关 |
| 内容状态不对 | `tools/opc-workflow validate`，再看内容卡与事件链 |
| 看板、日历、发布记录不对 | 重跑 `tools/opc-workflow build`；这些是 generated 只读视图，别手工编辑 |
| 工具链本身不通 | `tools/opc-smoke`（不读业务数据，缺目录也能跑） |
| 实例结构自检 | 实例里跑 `tools/opc-lint`（模版仓库的 `tests/` 是模版自检，实例里跑不通） |
| 机制文件被改过导致升级被拒 | `bin/opc upgrade` 打印的 diff；确认后由 owner 加 `--force-mechanism` |
| 权限被拒 | 上文「权限缺口」；技能被拒不算权限缺口，那是 `approvedSkills` 的事 |
