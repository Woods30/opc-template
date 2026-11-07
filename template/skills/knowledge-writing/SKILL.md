---
name: knowledge-writing
description: knowledge/ 的落盘规矩：目录归属、谁能写哪棵子树、决策与 inbox 记录方式、任务 ID 约定与取材范围。
---

# knowledge/ 落盘规矩

`knowledge/` 是这个实例的**唯一事实来源**。聊天记录、终端输出、owner 的口头结论都不算数，
结论必须落盘才能被下一个 session 读到。

## 目录分工

```text
knowledge/
├── content/      # canonical 内容包：内容卡、主稿、publications/，创建后不移动
├── business/     # 业务结果与 generated 只读视图
│   ├── <频道>/   # 由 channels.json 生成，只有 发布记录.md
│   ├── growth/   # 渠道计划、指标定义、渠道快照、转化路径
│   ├── product/  # 需求、方案、实现记录、已知问题
│   ├── 品牌口径.md
│   └── 选题日历.md
├── decisions/    # 决策与日志：裁决、阻塞解除、权限缺口
├── inbox/        # 任务队列：gm.md / content.md / growth.md / dev.md
└── work/<角色>/  # 过程材料：草稿、提案、实验记录、LESSONS.md
```

- `content/` 是**事实**：内容卡、主稿、渠道稿都在这里，靠记录表达状态。
- `business/` 是**结果与视图**：老板日常只看这里。频道目录只放 generated 发布记录，
  不放稿件或资产副本。
- `work/` 是**过程**：草稿、提案、日志都进版本库，但不是事实。
- `decisions/` 是**日志**，`inbox/` 是**队列**。两者不能混着当待办读。

## 谁能写哪棵子树

- 角色能写的子树由 `roles.json` 的 `scope` 决定，加上自己的 `knowledge/work/<角色>/`。
  权限层只挡「写不出实例目录」，**没有**替你锁住「只写自己那几棵子树」——那是你的责任。
- `knowledge/inbox/` 只有 gm 能写。其他角色把派工与上报交给 gm，由 gm 落盘。
- `knowledge/business/` 的定稿、`scripts/`、`tools/` 归 gm 与 owner，不要直接改。
- 内容区共享但写入受限：主稿、渠道稿与状态只能通过 `tools/opc-workflow` 写，
  指标观测同样走 workflow。

## 写决策

裁决、阻塞解除、权限缺口等写进 `knowledge/decisions/<YYYY-MM-DD>-<主题>.md`，三节固定：

```markdown
# <日期> · <主题>

## 决定
- <一句话说清决定了什么>

## 理由
- <为什么>

## 影响
- <受影响的角色、内容或 publication>
```

决策是日志，不是待办：写完不代表可以据此开工，动手前仍以 `inbox/` 里未标记的条目为准。

## 写 inbox 任务

派工由 gm 追加到 `knowledge/inbox/<角色名>.md`，一行一条，最新的在最下面：

```
- [YYYY-MM-DD HH:MM] 发起方：gm | 任务 ID：task-<小写字母数字> | 业务引用：<content_id 或 publication_id> | 任务：<做什么> | 验收：<怎么算完成>
```

- **任务 ID** 形如 `task-<小写字母数字>`，由 gm 分配且全实例唯一。后续改措辞、补验收时
  保持同一个 ID。没写时 workflow 会按「角色 + 时间 + 任务文本」派生一个稳定 ID。
- **业务引用** 指向这条任务服务的 canonical 记录，没有就填 `-`。
- 状态变化写回**派工所在的那个条目**：发起方收到完成回报后加 `✅`；撤销时加
  `⛔ 已撤销：<一句话原因>`。角色只执行行首既无 `✅` 也无 `⛔` 的条目。
- 追加完用 `hc send <前缀>-<角色名>` 通知对方；终端名先查 `knowledge/team.md`。

## 只在本实例目录内取材

业务事实只有 `knowledge/` 里的那些。实例目录外的路径默认不读不写：别的实例、
备份目录、旧实例残留都不是本实例的业务。名册（`knowledge/team.md`）之外的终端与本实例
无关，不要读它们的屏幕，也不要顺着它们显示的目录去找素材——那是另一份业务，读了既越界，
也可能把结论串味。要读实例外的东西，先向 gm 说明并拿到授权。

## 工具不改写业务事实

- 内容事实只由 `tools/opc-workflow` 写；工具不会替你改写、润色或「优化」已有事实。
- generated 只读视图由 `tools/opc-workflow build` 生成，标着
  `GENERATED FILE — READ ONLY`：`knowledge/business/选题日历.md`、各频道
  `发布记录.md`、`knowledge/business/dashboard.json`。它们坏了就重跑 `build`，
  不要手工编辑。
- 指标定义（`knowledge/business/growth/指标.md` 的 frontmatter）是指标的唯一来源：
  只写 key、label、unit、aggregation、scope 与适用 channels。观测值不写进指标定义，
  账号级观测也不归属到单个 publication。

## 命名与文风

- 目录是结构，用英文小写 ASCII slug；文件是内容，用中文。
- 命名带日期时用 `YYYY-MM-DD-` 前缀，例如 `knowledge/work/<角色>/YYYY-MM-DD-选题清单.md`。
- 中文写作，技术术语保留英文；中文与半角英数字之间加半角空格；标点用中文全角标点。
- 引用文件路径，不粘贴长内容；一次只说一件事。
- 过程产出写 `knowledge/work/<角色>/`，最终产出由 gm 搬进 `knowledge/business/`。
