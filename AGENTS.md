# OPC 模版开发规约

这是 **OPC 模版仓库**，不是实例。这里只放通用机制与模版开发材料；
真实业务长在各自的实例仓库里。`CLAUDE.md` 转发到这里。

## 三层模型

| 层 | 是什么 | 在哪 |
|---|---|---|
| 模版 | 通用机制、起始材料、全局 UI | 本仓库；`template/` 是运行载荷 |
| 实例 | 这一家的真实业务 | 每个实例自己的目录，由 `opc install` 生成 |

规则只有一条：**业务数据不进模版**。真实品牌名、频道 id、指标数字、客户资料、
实例状态（前缀、运行日志、审批）都不得出现在本仓库。

## 目录

```text
opc-template/
├── bin/opc                  # 唯一对外入口：install / upgrade
├── bin/opc_lib/             # 入口的实现（Python 标准库）
├── template/                # 运行载荷：会被复制/安装到实例与本机的东西
│   ├── install-manifest.json
│   ├── AGENTS.md            # 公司共享规约（起始材料，物化到每个实例）
│   ├── agents/ skills/      # 起始材料：角色目录与统一技能库，装一次就归 owner
│   ├── scripts/ tools/      # 机制：按指纹分发
│   ├── layouts/ mods/       # 全局 UI，只安装一份
│   └── seeds/               # 起始材料：业务种子，只补不覆盖
├── docs/                    # 模版开发文档与提案归档
├── tests/                   # 模版自检与沙箱测试
└── .opc-template-repo       # 模版标记：实例安装器见到它就会拒绝运行
```

外层其余文件（`README.md`、`AGENTS.md`、`.github/`、`.claude/commands/`）
只服务于模版开发，不会被复制进实例。

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

## 语言与格式

- 中文写作，技术术语保留英文；中文与半角英数字之间加半角空格。
- 标点用中文全角标点。
- 文档与代码注释解释「为什么」，不复述代码在做什么。

## 参考

- 安装、升级、迁移与缓存：[`docs/安装与升级.md`](docs/安装与升级.md)
- 实例内的公司规约：`template/AGENTS.md`
- 自检规则：`template/tools/opc-lint` 与 `template/install-manifest.json`
