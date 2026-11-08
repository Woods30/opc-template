---
name: knowledge-writing
description: knowledge/ 的落盘规矩：目录归属、谁能写哪棵子树、决策与任务卡记录方式、任务 ID 约定与取材范围。
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
│   ├── 选题池.md  # 候选条目池：单一副本，业务事实
│   └── 选题日历.md
├── decisions/    # 决策与日志：裁决、阻塞解除、权限缺口
├── tasks/        # 任务卡：<task_id>.md，一张卡一次派工
└── work/<角色>/  # 过程材料：草稿、提案、实验记录、LESSONS.md
```

- `content/` 是**事实**：内容卡、主稿、渠道稿都在这里，靠记录表达状态。
- `business/` 是**结果与视图**：老板日常只看这里。频道目录只放 generated 发布记录，
  不放稿件或资产副本。
- `work/` 是**过程**：草稿、提案、日志都进版本库，但不是事实。
- `tasks/` 是**派工**：任务卡是状态的唯一真源。`decisions/` 是**日志**，
  两者不能混着当待办读。
- `business/选题池.md` 是**业务事实**里的**单一副本**：候选条目与处置标记只存这一份，
  不复制到别处，也不散在 `work/` 里。

## 谁能写哪棵子树

- 角色能写的子树由 `roles.json` 的 `scope` 决定，加上自己的 `knowledge/work/<角色>/`。
  权限层只挡「写不出实例目录」，**没有**替你锁住「只写自己那几棵子树」——那是你的责任。
- `knowledge/tasks/` 下的任务卡由 `tools/opc-workflow` 的 `create-task` /
  `complete-task` / `cancel-task` 等命令维护：派工由编排者建卡，承接角色写完成态。
  这条分工是工具硬拦的——越权的写卡命令直接被拒。**不要手工编辑任务卡的 frontmatter**——
  完成态由工具原子写入，手改会与事实对不上。
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

决策是日志，不是待办：写完不代表可以据此开工，动手前仍以自己的任务卡为准。

## 写任务卡

一次派工 = 一张任务卡，落在 `knowledge/tasks/<task_id>.md`。**一张卡就是一次派工**，
不另建回报条目。

任务卡的 **frontmatter 是一个 JSON 对象**，字段固定：

| 字段 | 含义 |
|---|---|
| `schema_version` | 卡格式版本 |
| `record_type` | 固定 `"task"` |
| `task_id` | 任务 ID，形如 `task-<小写字母数字>`，全实例唯一 |
| `title` | 一句话标题 |
| `requester` | 发起方（通常是 gm） |
| `assignee` | 承接角色 |
| `created_at` | 创建时间 |
| `state` | `open` / `done` / `cancelled` |
| `reference` | 业务引用（content_id / publication_id），没有就写 `-` |
| `task` | **任务详情**：长需求写在这里 |
| `acceptance` | **验收标准**：做到哪算完 |
| `next` | **链边**：完成后交给谁 |
| `terminal` | **终点**：链条停在哪 |
| `events` | 事件链 |
| `completed_at` | 完成时间 |
| `result` | 结果：一句话结论与产出路径 |
| `cancel_reason` | 撤销原因 |

正文**极简**：`# 任务卡` 加一两行摘要。**长文本只放在前置字段里**，正文不复制一遍——
读卡时不必把大段需求灌进上下文。

命令族（`tools/opc-workflow`）的语义：

| 目的 | 命令 |
|---|---|
| 创建 | `tools/opc-workflow create-task --assignee <角色> --task "<详情>" --acceptance "<验收>" [--title "<标题>"] [--reference <业务引用>] [--next <下游角色>] [--terminal "<终点>"] [--task-id task-<id>] [--actor gm]` |
| 完成 | `tools/opc-workflow complete-task <task_id> --result "<一句话结论与产出路径>" [--completed-at "<offset-aware ISO 8601>"]` |
| 撤销 | `tools/opc-workflow cancel-task <task_id> --reason "<原因>"` |
| 列出 | `tools/opc-workflow list-tasks [--assignee <角色>] [--state open\|done\|cancelled]` |
| 读单张 | `tools/opc-workflow show-task <task_id>` |

- **任务 ID** 形如 `task-<小写字母数字>`，全实例唯一。`create-task` 不带 `--task-id`
  时按「承接角色 + 时间 + 任务文本」派生一个稳定 ID——同一张卡改措辞时 ID 不漂移。
- **完成是原子写**：完成时间与结果一起落盘，**缺结果或缺完成时间直接拒绝**，不允许写出
  「半个完成态」。同一张卡重复完成幂等，不产生第二条事实。
- **撤销写回卡片**：状态转 `cancelled` 并留下原因，不只写在决策文档里——否则重启后有
  角色会从旧日志把任务捞回来重做。
- 一条命令只做一件事：不要用 `;` 或 `&&` 串第二条命令。

### 委派契约

任务卡承载的是**边界**：详情、验收、链边、终点。

- **链边单向**：完成方直接通知下游角色，**不经编排者中转**。
- **链条到终点即停**：任何角色都不主动发起新一轮。
- **不设唤醒次数预算**：收敛靠卡上的边界，不靠计数器。

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
