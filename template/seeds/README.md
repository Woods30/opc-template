# OPC 实例

这是**你的实例**，不是模版。模版（通用机制、公开仓库）由全局 `opc` 命令管理；
这里装的是这一家的真实业务。

## 先看这两个文件

| 文件 | 内容 |
|---|---|
| `INSTANCE.md` | 本实例专属信息：前缀、频道、运行参数、已知待办 |
| `knowledge/team.md` | 团队名册：角色、终端名、各自能写哪块（自动生成） |

## 目录

```text
knowledge/           唯一事实来源
├── content/         canonical 内容包：内容卡、主稿、publications/
├── business/        结果、常驻口径与 generated 只读视图（频道目录只放发布记录）
├── work/<角色>/     过程：草稿、提案、日志、template-proposals/
├── decisions/       决策记录
└── inbox/           任务队列（只有 gm 可写；只执行行首既无 ✅ 也无 ⛔ 的条目）
```

`business/` 是结果，老板日常只看这里；`work/` 是过程，不干扰。
命名规则：**目录是结构，用英文；文件是内容，用中文**。
主稿与渠道稿从创建起就在对应内容包里，`work/` 只放非 canonical 过程材料。
通用素材放内容包的 `assets/`，渠道专用素材放对应 publication 包的 `assets/`。

## 日常

```sh
scripts/opc-up.sh        # 启动全部角色（owner 在自己终端跑）
scripts/opc-status.sh    # 看状态
scripts/opc-down.sh      # 停止
opc upgrade              # 在本目录升级到最新模版（先 --dry-run 看差异）
opc upgrade --all        # 升级注册表里的所有实例
tools/opc-workflow create-content --title "<标题>"  # 创建 canonical proposed 内容
tools/opc-workflow transition <content_id> --to drafting   # 创建固定主稿并进入写稿
tools/opc-workflow transition <content_id> --to reviewing  # 按主稿 hash 请求审核
tools/opc-workflow transition <content_id> --decision approved --actor gm  # 记录 owner 决定
tools/opc-workflow create-publication <content_id> --channel <channel> --actor gm  # 新建渠道发布
tools/opc-workflow transition <publication_id> --to reviewing --actor content     # 提交渠道稿审核
tools/opc-workflow transition <publication_id> --decision approved --actor gm     # 记录渠道稿决定
tools/opc-workflow transition <publication_id> --to scheduled --planned-at <ISO时间> --timezone <IANA时区> --actor gm
tools/opc-workflow transition <publication_id> --to published --actual-at <ISO时间> --url <URL> --actor gm  # 记录真实发布
tools/opc-workflow record-metrics <publication_id> --window 48h --observed-at <ISO时间> --source <来源> --values '<JSON>' --actor growth
tools/opc-workflow record-channel-snapshot --channel <channel> --observed-at <ISO时间> --source <来源> --values '<JSON>' --actor growth
tools/opc-workflow transition <publication_id> --to reviewed --conclusion <continue|iterate|stop|inconclusive> --next-action "<下一项行动>" --actor growth
tools/opc-workflow transition <content_id> --to closed --actor gm  # 必需 publication 全部复盘或带原因取消后关闭
tools/opc-workflow validate                         # 校验内容、publication、审批 hash 与指标
tools/opc-workflow build                            # 刷新 generated 业务视图与看板 JSON
tools/preflight <canonical 稿件路径>                # 发布前自检（也可 --content / --publication 按 ID）
```

owner 负责实际对外发布；gm 只把 approval 决定、发布时间与 URL 落盘。增长常驻内容分四类：
渠道策略在 `渠道计划.md`，指标定义在 `指标.md` frontmatter，账号级观测只由
`record-channel-snapshot` 写 `渠道快照.md`，转化路径在 `转化路径.md`。

## 业务看板

`build` 会写出 `knowledge/business/dashboard.json`：看板的只读 JSON 契约。
看板布局与 mod 是**全局安装**的：本机只装一份 `opc` / `opc-tabs` / `opc-dashboard`，
所有实例共用。Herdr space 的 folder 指向哪个实例，标签栏右上角就显示哪个实例的
「看板」入口；非 OPC 目录的 space 不显示这个按钮。看板只读，不改任何事实。
业务还没起步时看板是空的，那是正常状态，不是坏了。

## 与模版的关系

- 模版来源记在 `.opc/instance.json`；模版本体缓存在
  `~/.local/share/opc/template`，`opc install` / `opc upgrade` 会自动拉取最新版。
- 升级是单向的：模版 → 实例。升级不会碰 `knowledge/` 里你写的业务内容。
- 机制文件（`scripts/`、`tools/`）按指纹管理：本地直接改过会被升级拒绝并打印 diff。
- 起始材料（根 `AGENTS.md`、`agents/<角色>/`、`skills/`）装一次就归你：升级只更新你没改过
  的文件，改过的保留并告警，删掉的不复活，模版新增的才补入。
  想改模版的角色职责或技能，写提案到
  `knowledge/work/<角色>/template-proposals/`，格式见 `AGENTS.md` 的
  「模版与实例」一节。
- 骨架文件（README、LESSONS、`knowledge/business/` 下的初始文档）只在缺失时物化；
  升级不会覆盖你写过的版本，但你删掉的骨架会在下次升级时重新出现。
- 换一台机器重建这个实例：`opc install <目录> <前缀>`，再把 `knowledge/`
  与配置搬过去。

## 权限模型

每个角色一份 `.opc/settings-<角色>.json`，只放行本实例前缀的 `hc` 命令、
一组只读命令、以及角色自己子树内的写入。`git` / `rm` / `sudo` / `hc keys`
整类拒绝。完整说明见模版仓库的 README。

## 许可

脚本与规约沿用模版的 MIT 许可。
