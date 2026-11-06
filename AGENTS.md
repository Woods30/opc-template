# OPC 模版开发规约

这是 **OPC 模版仓库**，不是实例。这里只放通用机制与模版开发材料；
真实业务长在各自的实例仓库里。`CLAUDE.md` 转发到这里。

## 三层模型

| 层 | 是什么 | 在哪 |
|---|---|---|
| 机制 | 通用脚本与工具：实例生命周期、内容流程、校验工具、许可证 | `template/scripts/`、`template/tools/`、`template/LICENSE` |
| 起始材料 | 公司共享规约、角色目录、统一技能库、业务种子 | `template/AGENTS.md`、`template/agents/`、`template/skills/`、`template/seeds/` |
| 实例自有 | 真实业务、实例配置、运行状态 | 实例的 `knowledge/`、`roles.json`、`channels.json`、`.opc/` |

全局 UI（`template/layouts/`、`template/mods/`）跟着机制走，但只装一份到本机，
不复制进实例。

再加一条仓库层面的划分：模版仓库只放机制与起始材料，真实业务长在各自的实例仓库里。

规则只有一条：**业务数据不进模版**。真实品牌名、频道 id、指标数字、客户资料、
实例状态（前缀、运行日志、审批）都不得出现在本仓库。

## 目录

```text
opc-template/
├── bin/opc                  # 唯一对外入口：install / upgrade
├── bin/opc_lib/             # 入口的实现（Python 标准库）
├── template/                # 运行载荷：会被复制/安装到实例与本机的东西
│   ├── install-manifest.json
│   ├── AGENTS.md            # 起始材料：公司共享规约，物化到每个实例
│   ├── agents/<角色>/       # 起始材料：角色目录，入口是 AGENTS.md
│   ├── skills/<名字>/       # 起始材料：统一技能库，入口是 SKILL.md
│   ├── scripts/ tools/      # 机制：按指纹分发
│   ├── layouts/ mods/       # 全局 UI，只安装一份
│   └── seeds/               # 起始材料：业务种子，只补不覆盖
├── docs/                    # 模版开发文档与提案归档
├── tests/                   # 模版自检与沙箱测试
└── .opc-template-repo       # 模版标记：实例安装器见到它就会拒绝运行
```

外层其余文件（`README.md`、`AGENTS.md`、`.github/`、`.claude/commands/`）
只服务于模版开发，不会被复制进实例。

## 载荷清单

`template/install-manifest.json` 是分类与分发规则的**唯一来源**，五节：

| 节 | 装什么 | 分发方式 |
|---|---|---|
| `mechanism` | `scripts/`、`tools/` 目录与 `LICENSE` | 整目录覆盖，SHA-256 指纹校验 |
| `starters` | 根 `AGENTS.md`、`agents/`、`skills/` | 装一次归 owner，升级按基线比对 |
| `config` | `roles.json`、`channels.json` | 按键合并，只增不改，新条目默认停用 |
| `seeds` | 业务骨架文件 | 只补不覆盖 |
| `ui` | 布局与 mod | 全局安装一份，名称固定 |

`starters.dirs` 里 `skills` 标了 `"type": "skill"`，因此它的每个子目录是一个
**技能单元**：整目录冻结，不按文件更新。`agents` 没有 `type`，按文件管理。
新增或删除载荷文件要同步改这份清单，`bin/opc lint --strict` 会查。

## 命令

```sh
bin/opc install <实例目录> [前缀]   # 新建实例；首次会链 ~/.local/bin/opc
bin/opc upgrade [实例目录]          # 升级当前/指定实例
bin/opc upgrade --all               # 升级注册表里的全部实例
bin/opc ls                          # 看注册表
bin/opc lint --strict               # 模版自检
bin/opc paths --json                # 诊断本机路径
```

模版本体首次使用时会缓存到 `~/.local/share/opc/template`，`install` /
`upgrade` 默认先拉取远端最新版。开发本仓库时设 `OPC_TEMPLATE=$PWD` 或加
`--template .`，就会直接用工作区代码、不拉取。

## 改模版时

1. **先改载荷**：机制改动落在 `template/`；`install-manifest.json` 是分类与
   分发规则的唯一来源，新增/删除文件要同步改它。
2. **机制文件按指纹分发**：实例里的 `scripts/`、`tools/`、`LICENSE` 由
   `upgrade` 整目录覆盖；实例本地改过会被拒绝，所以不要依赖实例侧的手工修补。
3. **起始材料按基线更新**：`AGENTS.md`、`agents/`、`skills/` 与 `seeds/` 装一次
   就归 owner。实例用 `.opc/starters.json` 记基线：没改过的跟随模版更新，
   改过的保留并告警，删掉的不复活，模版新增的补入。技能目录整目录冻结，
   角色目录按文件管理。
4. **角色是目录**：角色材料在 `template/agents/<角色>/AGENTS.md`，纯 Markdown，
   目录里可放角色专属参考文件。角色元数据（描述、技能选择、权限）都在
   `template/roles.json`；hc 模板的 frontmatter 由安装器按它拼出来，不要
   写回角色文件。
5. **UI 全局唯一**：布局名固定为 `opc` / `opc-focus` / `opc-grid` /
   `opc-monitor`，mod 名固定为 `opc-dashboard` / `opc-tabs`。布局与 mod 里
   不得留 `{{...}}` 占位，也不得带实例前缀。
6. **不写实例状态**：本仓库不产生 `.opc/`、`knowledge/`、`template.lock.json`；
   它们只属于实例。
7. **改完跑自检**：`bin/opc lint --strict` 必须全绿；涉及安装/升级的改动再加
   沙箱测试（`tests/`）。提交只包含本次改动，不要顺手带上无关文件。

## 加一个角色

1. 建 `template/agents/<角色>/AGENTS.md`：纯 Markdown，带 `## 启动` 小节，
   写明「等 gm 派工」（gm 写「先与 owner 对齐方向」）；正文里写清职责与边界。
   取材范围要有一行加粗的项目符号：`- **只在本实例目录内取材**：…`——
   lint 认的是这个句式，散在散文里的同义表述不算数。
2. 在 `template/roles.json` 加一条：`name`、`enabled`、`cli`、`description`、
   `template`（`agents/<角色>/AGENTS.md`）、`skills`、`permissionMode`、
   `scope`、`approvedSkills`。模版里通常写 `enabled: true`，让新实例开箱可用；
   已有实例升级时新角色按 `append-disabled` 追加，默认停用，由 owner 决定启用。
3. 角色要用的技能在 `template/skills/<名字>/` 下建目录，写 `SKILL.md`：
   frontmatter 要有 `name`（与目录名一致）与 `description`（单行）。
4. 跑 `bin/opc lint --strict`：角色正文与技能 frontmatter 都在模版侧检查范围内。

## 加一个技能

1. 建 `template/skills/<名字>/SKILL.md`，frontmatter 有 `name`（与目录名一致）
   与 `description`（单行）；正文写清楚这套做法什么时候用、怎么做。
2. 技能目录里可以放配套文件，但它们与 `SKILL.md` 一起构成一个单元——升级时
   整目录冻结或整目录更新，不会半新半旧。
3. 在 `template/roles.json` 里给要用它的角色填 `skills`。技能**不链接**到
   `.claude/skills/` 或 `.agents/skills/`，靠 hc 模板的技能索引加按需读取加载。
4. `approvedSkills` 管的是 CLI 原生技能的调用权限，与根级技能库是两回事，
   不要混用。

## 语言与格式

- 中文写作，技术术语保留英文；中文与半角英数字之间加半角空格。
- 标点用中文全角标点。
- 文档与代码注释解释「为什么」，不复述代码在做什么。

## 参考

- 安装、升级、迁移与缓存：[`docs/安装与升级.md`](docs/安装与升级.md)
- 实例内的公司规约：`template/AGENTS.md`
- 自检规则：`template/tools/opc-lint` 与 `template/install-manifest.json`
