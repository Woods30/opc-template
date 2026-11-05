# OPC 实例

这是**你的实例**，不是模版。模版（通用机制、公开仓库）在本机另一处；
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
├── business/        结果、常驻口径与 generated 只读视图
├── work/<角色>/     过程：草稿、提案、日志、template-proposals/
├── review/          非 canonical 对外物料的待审区；主稿审核不使用
├── decisions/       决策记录
├── daily/           每日汇总
└── inbox/           任务队列（只执行行首既无 ✅ 也无 ⛔ 的条目）
```

`business/` 是结果，老板日常只看这里；`work/` 是过程，不干扰。
命名规则：**目录是结构，用英文；文件是内容，用中文**。

## 日常

```sh
scripts/opc-up.sh        # 启动全部角色（owner 在自己终端跑）
scripts/opc-status.sh    # 看状态
scripts/opc-down.sh      # 停止
scripts/opc-sync.sh check   # 看模版有没有更新
scripts/opc-sync.sh pull    # 拉取模版更新
tools/opc-workflow create-content --title "<标题>"  # 创建 canonical proposed 内容
tools/opc-workflow transition <content_id> --to drafting   # 创建固定主稿并进入写稿
tools/opc-workflow transition <content_id> --to reviewing  # 按主稿 hash 请求审核
tools/opc-workflow transition <content_id> --decision approved --actor gm  # 记录 owner 决定
tools/opc-workflow create-publication <content_id> --channel <channel> --actor gm  # 新建渠道发布
tools/opc-workflow transition <publication_id> --to reviewing --actor content     # 提交渠道稿审核
tools/opc-workflow transition <publication_id> --decision approved --actor gm     # 记录渠道稿决定
tools/opc-workflow transition <publication_id> --to scheduled --planned-at <ISO时间> --timezone <IANA时区> --actor gm
tools/opc-workflow validate                         # 校验内容、publication 与审批 hash
tools/opc-workflow build                            # 刷新 generated 业务视图
```

## 与模版的关系

- 模版在本机的位置记在 `.opc/instance.json`；也可以用 `--from <路径>` 显式指定。
- 同步是单向的：模版 → 实例。同步不会碰 `knowledge/` 里你写的业务内容。
- 想改模版，**不要直接改**这里的机制文件（`scripts/`、`tools/`、`agents/`、
  `AGENTS.md`）。写提案到 `knowledge/work/<角色>/template-proposals/`，格式见
  `AGENTS.md` 的「模版与实例」一节。
- 换一台机器重建这个实例：`scripts/opc-new.sh <目录> <前缀>`，再把
  `knowledge/` 与配置搬过去。

## 权限模型

每个角色一份 `.opc/settings-<角色>.json`，只放行本实例前缀的 `hc` 命令、
一组只读命令、以及角色自己子树内的写入。`git` / `rm` / `sudo` / `hc keys`
整类拒绝。完整说明见模版仓库的 README。

## 许可

脚本与规约沿用模版的 MIT 许可。
