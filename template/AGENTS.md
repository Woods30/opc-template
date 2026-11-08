# OPC 公司共享规约

本文件是 **OPC 各角色 agent 的统一入口**。默认角色是 gm / content / growth / dev，
但角色是配置：以 `roles.json` 为准，当前启用了哪些、各自终端名叫什么，见
`knowledge/team.md`。`CLAUDE.md` 与 `GEMINI.md` 转发到这里；角色专属的职责与边界写在
`agents/<角色>/AGENTS.md` 正文里，不在此重复。

## 公司定位

OPC 是一家一人公司，业务为**内容/自媒体 + 技术研发**两条线：

- **内容线**：公众号、X、图文平台等渠道的内容生产与分发。**具体频道清单见
  `channels.json`**，本文不硬编码。
- **技术线**：公司需要的一切技术研发工作——脚本与自动化、内部工具、数据管道、
  项目开发（官网、SaaS、服务）。不限于「面向内容的产品」。

四条线角色划分：gm（总经理）负责定方向与裁决，content 负责内容，growth 负责增长，
dev 负责研发。

## 语言与格式

- 中文写作，技术术语保留英文。
- 中文与半角英数字之间加半角空格。
- 标点用中文全角标点。

## 目录结构

```text
knowledge/
├── content/      # canonical 内容包：内容卡、主稿、publications/，创建后不移动
├── business/     # 业务结果与 generated 只读视图：老板日常只看这里
│   ├── <频道>/   # 由 channels.json 生成，只有 发布记录.md
│   │   └── 发布记录.md
│   ├── growth/   # 渠道计划、指标目录、渠道快照、转化路径、实验
│   ├── product/  # 需求、方案、实现记录、已知问题
│   ├── 品牌口径.md
│   ├── 选题池.md  # 候选条目池：单一副本，业务事实
│   ├── 选题日历.md
│   └── dashboard.json  # generated 只读视图：看板 JSON 契约（build 生成）
├── decisions/    # 决策记录（gm 裁决后落盘）
├── tasks/        # 任务卡：<task_id>.md，一张卡一次派工
└── work/<角色>/  # 过程：草稿、提案、实验记录、LESSONS.md
    └── template-proposals/  # 给模版提的改进提案（见「模版与实例」）

agents/<角色>/    # 角色材料目录
└── AGENTS.md     # 角色入口：职责、边界、工作方式、启动小节
skills/<名字>/    # 统一技能库
└── SKILL.md      # 技能说明；角色按 roles.json 的 skills 选用
```

- `agents/<角色>/AGENTS.md` 是该角色的入口文件，纯 Markdown，不带 hc frontmatter。
  目录里还可以放角色专属参考文件（清单、示例、参考稿），按路径读取即可。
- `skills/<名字>/SKILL.md` 是**根级统一技能库**：所有角色共用一份事实源。角色
  启动提示里只列出自己选中的技能（名字、一句话用途、路径），需要时再读具体文件，
  不用把全部技能塞进上下文。
- 实例默认带三个技能：`opc-workflow`（内容生命周期怎么推）、`knowledge-writing`
  （`knowledge/` 怎么落盘）、`instance-ops`（实例怎么跑、怎么查）。角色在
  `roles.json` 的 `skills` 里选用，索引只列选中的。
- 你的技能索引在启动提示的「技能索引」一节里，每条给出名字、用途与
  `skills/<名字>/SKILL.md` 路径。**动手做对应的事之前先读那个文件**——那是这套做法
  的权威说明，不要凭印象重造流程。索引里没有的技能不要自己找来源。
- 根级技能库不链接到 `.claude/skills/` 或 `.agents/skills/`，靠索引加按需读取加载；
  `roles.json` 的 `approvedSkills` 管的是 CLI 原生技能的调用权限，与根级技能库是两回事。

- `content/` 是**事实**：每条内容从 proposed 起固定在 `<content_id>/内容卡.md`，不靠移动目录表达状态。
  主稿固定在 `<content_id>/主稿.md`，渠道稿固定在
  `<content_id>/publications/<publication_id>/渠道稿.md`。
- **素材归属**：跨渠道复用的通用素材放内容包的 `<content_id>/assets/`；只在某个渠道用的
  素材放该 publication 包的 `publications/<publication_id>/assets/`。素材跟着内容走，
  不复制到 `business/<频道>/`（那里是 generated 视图），也不堆在 `work/`（那里是过程材料）。
- `business/` 是**结果与视图**：成稿、常驻口径，以及 generated 只读视图。老板只看这里。
  频道目录只放 generated 发布记录，不放稿件或资产副本。
- `work/` 是**过程**：草稿、提案、日志。老板不看，但进版本库。
- 不再有 `review/` 与 `daily/`：审核状态写在 canonical 记录里，决策写 `decisions/`。

命名规则：**目录是结构，用英文；文件是内容，用中文**。目录一律小写 ASCII slug。

`knowledge/` 是唯一的事实来源。**结论必须落盘**，聊天与终端里的内容不算数。

## 模版与实例

OPC 分两层仓库、三层载荷。

仓库层面：**模版**（通用机制与起始材料，公开仓库）与**实例**（这一家的真实业务，
本地仓库）。角色在**实例**里运行。

载荷层面，实例里的东西分三层，各有各的归属：

| 层 | 内容 | 归谁 |
|---|---|---|
| 机制 | `scripts/`、`tools/` | 模版：升级整目录覆盖，本地改过会被拒绝 |
| 起始材料 | 根 `AGENTS.md`、`agents/<角色>/`、`skills/<名字>/` | owner：装一次就归 owner，升级只更新没改过的 |
| 起始材料 | 业务种子 | owner：只补不覆盖，已有的不更新，删掉的不复活 |
| 实例自有 | `knowledge/`、`roles.json`、`channels.json`、`.opc/` | 实例：业务内容不动，配置只增不改，运行状态由工具重建 |

- 模版里的占位骨架随模版分发，开实例时由 `opc install` 物化到本目录的
  `knowledge/business/` 等位置。物化之后通常归业务所有；标有
  `GENERATED FILE — READ ONLY` 的文件例外，只能通过对应生成命令刷新。
- **发现模版要改，不要在实例里直接改模版文件**（脚本、简报、规约）。改实例的
  副本会在下一次升级时被拒绝（机制文件按指纹校验），而且会把模版和业务的改动搅在一起。
- 起始材料（`AGENTS.md`、角色目录、技能库）改起来是安全的：升级只更新你没改过的
  文件，改过的保留并告警，删掉的不复活，模版新增的才补入。但**技能目录例外**：
  技能以目录为单位冻结，目录里任一文件被改过，整个技能就不再更新。业务种子更保守：
  只补不覆盖，实例里已有的永远不随模版更新。
- 正确做法是写**提案**：`knowledge/work/<角色>/template-proposals/<YYYY-MM-DD>-<主题>.md`，
  五个固定小节——`## 现象`、`## 泛化需求`、`## 期望模版改动`、`## 影响文件`、
  `## 脱敏自检`。任何角色都能提，不必等 dev。
- **脱敏是硬要求**：提案里只讲机制与流程，不出现真实品牌名、真实频道 id
  （wechat/x/zhihu…）、真实数字指标。要举例就用 `<占位>`。
- 提案先由 gm 汇总进 `knowledge/decisions/`，owner 脱敏后人工搬进模版仓库。
- `scripts/` 与 `tools/` 是执行面，只有 owner 能改；角色改不了，也不要绕。

## 协作协议

### 委派契约

派工的载体是**任务卡**：`knowledge/tasks/<task_id>.md`。**一张卡就是一次派工**，
不另建回报条目。

任务卡承载的是边界，不是摘要：

| 边界 | 写在卡上的哪一处 |
|---|---|
| 详情 | 任务正文（长需求写在这里，不压成一行摘要） |
| 验收 | 做到哪算完 |
| 链边 | 完成后交给谁 |
| 终点 | 链条停在哪 |

四条规矩：

1. **链边单向直送下游**：完成方直接通知下游角色，**不经编排者中转**。编排者不是
   中转站——它只做判断，不替别人搬运事实。
2. **链条到终点即停**：到达终点就停（终点可以是「等待 owner 决定」这种外部依赖），
   任何角色都不主动发起新一轮。
3. **不设唤醒次数预算**：收敛靠任务卡上的边界，不靠计数器。边界写清楚了链条就停得住；
   边界没写清楚是派工的问题，不是多跑几轮的问题。
4. **任务卡是状态的唯一真源**：`decisions/` 与 `work/` 里的历史描述不作为「现在该做什么」
   的依据——它们记录的是当时的状态，可能早已被推翻。

任务卡格式与命令族见 `skills/knowledge-writing/SKILL.md` 的「写任务卡」一节。

### 派工

编排者是**唯一**有权派工的角色。派工 = 建一张任务卡 + 委派：

1. 用 `tools/opc-workflow create-task` 创建任务卡。卡上写清详情、验收、链边、终点。
2. 委派：把卡交给承接角色，让它知道**边界**（做到哪算完、交给谁）。委派消息只带
   一句话与卡路径，长需求留在卡里。

```sh
hc send <前缀>-<角色名> "任务已派：见 knowledge/tasks/<task_id>.md"
```

`<前缀>` 是本实例的项目前缀，`knowledge/team.md` 里有准确名字——**发消息前先查名册**，
不要凭记忆拼终端名。

链边上的下游角色**不需要**经过编排者：卡上写了交给谁，完成方就直接通知谁。

### 执行

承接角色被唤醒后，只读**三件套**（见「记忆注入」）加本次任务的详情，然后动手。
产出分三种：

- **过程**（草稿、提案、实验记录）写 `knowledge/work/<角色名>/`；
- **内容事实**通过 `tools/opc-workflow` 写入 `knowledge/content/<content_id>/`；
- **常驻表**（`business/品牌口径.md`、`business/growth/指标.md` 等）由所属角色直接维护。

`knowledge/business/选题日历.md` 是 generated 只读视图；运行 `tools/opc-workflow build`
从内容卡刷新，不得手工编辑。日历分两节：**待排期选题**放没有目标日期的活跃内容，
**已排期内容**放有目标日期的活跃内容；已关闭与已取消的内容是历史，不进日历，
去内容卡或看板历史里看。内容卡里的 actor 只能是自己的 role key（默认取
`OPC_ROLE`），不得冒充其他角色。

完成后**回报只是通知**——通知链边上的下游角色（链边为空则通知编排者），不另建回报条目：

```sh
hc send <前缀>-<下游角色或gm> "完成：<一句话结论> | 产出：<文件路径>"
```

`hc send` 不携带状态。**完成态由工具写入任务卡**：完成时间与结果由命令原子落盘，
缺结果或缺完成时间时命令直接拒绝，不允许写出「半个完成态」；同一张卡重复完成是
幂等的，不会产生第二条事实。

撤销也写在任务卡上（`state` 转 `cancelled` 并留下原因），不只写在决策文档里——
否则重启后有角色会从旧日志把任务捞回来重做。

### 编排者的触发

编排者只做判断，不做记账。它只在三种情况下被唤醒：

1. **owner 直接下指令**；
2. **角色请求裁决**（拿不准、互相冲突、越界）；
3. **任务链到达审批点**。

没有这三种情况时，编排者**不主动读任何角色的目录**，不预读别人的卡，也不自己找活干。
空闲不是开工的理由。

### 主稿审核

1. content 用 `tools/opc-workflow transition <content_id> --to drafting` 进入写稿，主稿固定在
   `knowledge/content/<content_id>/主稿.md`；`work/` 只放非 canonical 过程材料。
2. 写完运行 `transition <content_id> --to reviewing`，workflow 把主稿 SHA-256 写进
   pending approval；随后 `hc send` 通知 gm。
3. gm 向 owner 确认决定，并用 `transition <content_id> --decision
   <approved|changes_requested|rejected> --actor gm` 落盘。退回或拒绝必须带 `--note`。
4. approved 才进入 ready。审批后修改主稿会被 `validate` 判为 `stale approval`；在同一文件
   修改后重新提交、重新审批，旧决定保留在 events。
5. 主稿不移动、不复制到 `business/`；`knowledge/business/选题日历.md` 只由
   `tools/opc-workflow build` 生成当前状态与目标日期视图。

### 渠道 publication

1. 主稿 ready 后，gm 运行 `tools/opc-workflow create-publication <content_id> --channel
   <channel> --actor gm`。channel 必须来自 `channels.json` 且已启用。
2. 渠道稿固定在 `knowledge/content/<content_id>/publications/<publication_id>/渠道稿.md`；
   content 完成后用 `transition <publication_id> --to reviewing --actor content` 请求审核。
3. gm 向 owner 确认并用 `--decision` 落盘。只有有效 approved 渠道稿才能 scheduled；审批后
   改稿会 stale，必须重新提交和审批。
4. 首次排期提供 `--planned-at` 与 IANA `--timezone`。scheduled 后再次排期还必须带
   `--note` 记录原因；发布前取消用 `--to cancelled --note <原因>`，保留 publication 记录。
5. 各频道 `knowledge/business/<channel>/发布记录.md` 是 generated metadata view，只含状态、
   排期与 canonical links，不复制稿件、审批说明或资产。

### 发布确认与增长观测

1. owner 完成外部发布后，gm 用 `transition <publication_id> --to published --actual-at
   "<offset-aware ISO 8601>" --url "<HTTP(S) URL>" [--external-id "<平台 ID>"] --actor gm`
   确认。只有 scheduled publication 可以确认；计划时间保留在 `schedule`，实际发布时间、
   URL 与记录时间写入 `publication`，两者不互相覆盖。
2. published publication 不能退回发布前状态。同一内容再次发布必须新建 publication，
   旧记录保持 published，历史与指标归属不丢。
3. growth 维护 `knowledge/business/growth/指标.md` 的 frontmatter，作为指标定义的唯一来源：
   每个 metric 声明 key、label、unit、aggregation、scope（publication / channel）与
   适用 channels。观测值不写进指标定义。
4. growth 用 `record-metrics <publication_id> --window 48h --observed-at "<offset-aware ISO
   8601>" --source "<来源>" --values '{"<metric_key>": 数值}' --actor growth` 为 published
   publication 追加窗口。同一 publication 的同一窗口不可覆盖；未知 key、scope/unit 不匹配、
   缺失来源与重复窗口都会被拒绝。
5. 账号级观测（粉丝总量、账号流量等）用 `record-channel-snapshot --channel <channel>
   --observed-at "<offset-aware ISO 8601>" --source "<来源>" --values '{"<metric_key>": 数值}'
   --actor growth` 写入独立 `knowledge/business/growth/渠道快照.md`，不得归属到单个
   publication。
6. `build` 的频道视图区分指标缺失（未记录）、不可得（`{"available": false, "reason":
   "..."}`）与数值为零；渠道账号观测单独成节，不混入 publication 指标。

### 增长常驻规则

growth 的四类常驻内容分开放，不互相代替：

| 内容 | 位置 | 写法 |
|---|---|---|
| 渠道策略 | `business/growth/渠道计划.md` | growth 直接维护：定位、节奏、内容形式偏好 |
| 指标定义 | `business/growth/指标.md` frontmatter | growth 直接维护；只写 key、label、unit、aggregation、scope 与 channels |
| 账号级渠道快照 | `business/growth/渠道快照.md` | 只能由 `record-channel-snapshot` 追加，不手改 |
| 转化路径 | `business/growth/转化路径.md` | growth 与 dev 共同维护：从曝光到转化的路径与卡点 |

观测值永远不进指标定义；账号级数据不归属到单个 publication。

### 复盘与关闭

1. publication 创建时用 `--required-window 48h`（可重复）声明必需指标窗口；`--optional`
   表示该 publication 不参与内容关闭判定，且不得声明必需窗口。默认是必需 publication。
2. 发布后由 growth 完成复盘：`transition <publication_id> --to reviewed --conclusion
   <continue|iterate|stop|inconclusive> --next-action "<下一项行动>" --actor growth`。
   必需窗口的数据都已记录才能进入 reviewed；`review` 引用实际存在的指标窗口，不改写
   历史指标。
3. 数据确实不可得时（如平台不提供历史窗口），由 gm 带 `--exception-reason "<原因>"`
   完成复盘；例外写进 review 与事件链，成为关键业务事件。
4. 内容关闭由 gm 执行：`transition <content_id> --to closed --actor gm`。只有 ready 内容
   可以关闭；所有必需 publication 必须已 reviewed 或已带原因 cancelled，否则命令失败并
   列出阻塞项。可选 publication 不阻塞关闭。
5. 选题作废由 gm 执行：`transition <content_id> --to cancelled --note "<原因>" --actor
   gm`。只有 proposed 或 drafting 内容可以取消，取消是终态，内容卡保留取消记录与事件。
6. 完成复盘与关闭内容会刷新生成的选题日历与渠道发布记录，但不修改任何历史指标快照。

### 阻塞

阻塞不是生命周期状态，是内容卡上的独立对象：

- 记录：`block <content_id> --reason "<原因>" --actor content`，只有 gm 与 content 能记。
- 解除：`unblock <content_id> [--note "<解除说明>"] --actor gm`。
- 阻塞是硬闸门：受阻内容不再往前走——写稿、请求审核、记录审批、创建 publication、排期
  都会被拒绝，先解除阻塞或作废再继续。已发布事实、指标记录与复盘不受影响。
- gm 记录的阻塞只有 gm 能解除；content 记录的阻塞 gm 或 content 都能解除。
- 阻塞与解除都写进事件链；阻塞不改变生命周期状态，看板会把受阻内容标出来并放进紧急项。

### 内容闭环总览

```text
proposed        content 用 create-content 创建内容卡
  ↓ drafting    content 在固定主稿写稿
  ↓ reviewing   content 提交，workflow 记录主稿 SHA-256
  ↓ ready       gm 记录 owner 的 approved
  ↓ adapting    gm 用 create-publication 为渠道建 publication
  ↓ reviewing   content 提交渠道稿，workflow 记录渠道稿 SHA-256
  ↓ scheduled   gm 记录 owner 决定并排期
  ↓ published   owner 实际发布，gm 用 --to published 落盘时间与 URL
  ↓ metrics     growth 用 record-metrics / record-channel-snapshot 记录观测
  ↓ reviewed    growth 复盘（结论 + 下一项行动）；数据不可得时 gm 记例外
  ↓ closed      gm 在所有必需 publication 复盘或带原因取消后关闭内容

proposed / drafting --cancelled--> gm 带原因取消选题，终态
```

owner 负责实际对外发布；gm 负责把 approval 决定与发布事实落盘，不代替 owner 发布。

### 业务看板

1. `tools/opc-workflow build` 还写出 `knowledge/business/dashboard.json`：看板的只读
   JSON 契约，只含 metadata（状态、时间、路径、指标摘要），不含主稿、渠道稿与复盘正文。
   它是 generated 只读视图，不得手工编辑；坏了就重跑 `build`。
2. 看板是全局安装的 herdr mod（`opc-dashboard`），只读这份 JSON，不遍历也不解析
   canonical Markdown，也不承担任何业务写入——canonical 记录的写入仍然只有 workflow
   命令；看板最多重跑一次 `build` 刷新 generated 视图。
3. 看板的入口在标签栏右上角（全局 `opc-tabs` 是 Herdr 自带 `tabs` 的副本，多一个
   「看板」按钮，跟 Files / Changes 平级；只在 space 的 folder 是 OPC 实例时出现）：
   点开是看板 tab，再点一下关掉。业务还没
   起步时看板是空的，那是正常状态；只有缓存读不到或 JSON 坏了才报红。
4. 看板默认视图聚焦未关闭或受阻内容、待审批、开放任务，以及未完成指标/复盘、近期发布
   与近期计划的 publication；历史默认不计入，避免旧数据污染 KPI。
5. 看板点条目时只读预览对应的 canonical 源文件；点角色时按 `knowledge/team.md` 里的
   **准确终端名**找到那个终端并聚焦，不按命名规则猜地址；打不开文件或终端时只提示
   可恢复的错误，不改业务状态。

### 权限缺口

角色默认跑在 `bypassPermissions`：**没有弹窗，也没有 allow 规则兜底**。仍然拦得住的
只有三层——`deny` 规则（`git` / `rm` / `sudo` / `hc keys` + 凭据路径）、
文件工具的工作目录写入封锁（写不出实例目录）、Claude Code 自己的保护路径。
被拒时按顺序处理：

1. **先换写法**——用已放行的只读命令组合完成，或改用 `tools/` 里的包装器。
   不要反复重试同一条被拒的命令。
2. **换不了就上报**，不要硬扛、不要自己去找绕过的命令。用 `hc send` 发给 gm：

   ```sh
   hc send <前缀>-gm "权限缺口：<完整命令> | 场景：<要做什么> | 已尝试：<替代方案>"
   ```

   **不要直接改别人的任务卡**——`knowledge/tasks/` 下的卡由 `tools/opc-workflow`
   的 `create-task` / `complete-task` / `cancel-task` 等命令维护，绕过命令手改会让
   完成态与事实对不上。gm 在会话里收到后处理，汇总进当天的决策记录（见下一条）。

3. gm 把它汇总到当天的 `decisions/<日期>-权限缺口.md`；owner 批量处理后重跑
   `scripts/opc-install.sh`，受影响的角色重启一次即可。

**技能被拒不算权限缺口**：技能只放行 `roles.json` 里该角色 `approvedSkills` 列出的
名字（生成精确的 `Skill(<名字>)` 规则，不放行裸 `Skill`——技能的 `allowed-tools`
会在调用那一轮临时预授权工具）。报「Permission to use Skill has been denied」时，
让 gm 记下来、owner 把技能名加进 `approvedSkills` 后重跑安装。
`bypassPermissions` 下 allow 规则不生效，技能本来就能调——被拒说明是技能本身没被发现
（claude 查 `.claude/skills/` 与 `~/.claude/skills/`，codex 查 `.agents/skills/` 与
`~/.agents/skills/`）。改用等效的手工做法继续，不要反复请求调用。

**新增能力的三条固定路径**（白名单只能由 owner 改 `scripts/`）：

| 要加的东西 | 谁做 | 生效方式 |
|---|---|---|
| 只读命令 | owner 改 `opc-install.sh` 的 `readonly_rules` | 重跑安装 + 重启角色 |
| 新工具 `tools/<名字>` | dev 在 `knowledge/work/dev/tools/` 写提案与测试，owner 审过 `git mv` 进 `tools/` 并加 `Bash(./tools/<名字>:*)` | 重跑安装 + 重启角色 |
| 新角色 | `scripts/opc-role.sh add` | 新角色默认 `default` 模式，跑通一轮后再切 `dontAsk` |
| 新频道 | 改 `channels.json` | 重跑安装 |

**`tools/` 与 `scripts/` 同级，都只有 owner 能写。** 任何被白名单放行的可执行文件，
如果角色还能改写它，白名单就形同虚设——改文件即等于拿到它的全部权限。所以工具一律
先写提案（`knowledge/work/dev/tools/`），owner 落盘并加白名单后才可执行。

同理**不要**用通配符放行 `Bash(./tools/*)`：那是把执行权一次签发给所有工具，
包括将来任何被放进来的东西。

### 越界与冲突

拿不准、与其他角色冲突、或超出自身职责时：**不要自行决定**。`hc send <前缀>-gm`
说明情况（终端名见 `knowledge/team.md`），由 gm 在当前会话里处理并决定
——**派工只有编排者能做**，其他角色不自行派工、不自行写别人的任务卡。

### 消息格式

- 短句，先结论后细节。
- 一次只说一件事。
- 引用文件路径，不要粘贴长内容。
- 收到的消息带 `<hc from="t1x opc-content">` 标签，这是 hc 的通知格式，忽略标签本身即可。

### 角色终端名

每个角色是一个 `hc` 终端，名字格式为 `<项目前缀>-<角色>`（例如项目 `opc` 下的
`opc-gm`）。**当前实例的完整名册在 `knowledge/team.md`**，那是唯一权威来源——
`hc send` 要用准确的名字，用之前先查它。

终端内 `$HC_TERMINAL_ID` 是自己的地址，可用于自报家门。`hc ls` 列出**全部** live 终端——
别的实例、别的项目空间，还有目录已经被删掉却还挂着的残终端，都会出现在里面。
**只有名册里的 `<前缀>-<角色>` 才是本实例的终端**；名册之外的终端与本实例无关，
不要读它们的屏幕，也不要顺着它们显示的 cwd 去别的目录找东西。

## 通用工作约定

- **只在本实例目录内取材**：业务事实只有 `knowledge/` 里的那些。实例目录外的路径（别的实例、
  备份目录、旧实例残留）默认不读不写；别处看到同名目录，也不要参考同类实例——
  那是另一家的业务，读了既越界，也可能把结论串味。要读实例外的东西须先向 gm 说明并拿到授权。
- **验证主流程用 `tools/opc-smoke`**：它不读实例的业务数据，缺目录也能跑。
  模版仓库的 `tests/` 是**模版自检**，依赖模版标记，在实例里跑必然失败——不要在实例里跑那一套。
- **先读后写**：动手前先读相关文件，不凭猜测改文件。
- **产出落盘**：过程写 `knowledge/work/<角色>/`，最终产出由 gm 搬进 `knowledge/business/`；
  命名带日期，如 `2026-11-04-选题清单.md`。
- **不越权**：不擅自发布对外内容、不擅自承诺预算、不擅自改业务优先级、不擅自对外承诺。
- **遇到问题上报**，而不是硬扛或自行拍板。
- **向 owner 提问用普通文本**，不用阻塞式交互界面：界面挂着的时候终端不接收新输入，
  其他角色的完成回报就投不进来，整条上报链会停摆。
- **不启动子 agent**，除非 gm 明确指派。
- **不修改本文件与 `CLAUDE.md`、`GEMINI.md`**；规约变更由 gm 决定。
- **写文件用 Edit/Write 的既定工具**，不要用 shell 重定向改内容。
- **一条命令只做一件事**：不要用 `;` / `&&` 把第二条命令串上去（如 `cmd; echo "exit=$?"`）。
  复合命令会被拆成子命令逐条判定，白名单外的子命令照样弹审批——`echo` 不在白名单
  （`echo > file` 能写文件，会绕过 Edit 子树隔离），挂在命令尾巴上就多一次审批。
  要退出码直接看工具返回里带的退出码，不要另起一条 `echo`。
- **跨终端读屏用终端名**：`hc read <前缀>-content`，不要用 `hc ls` 里给的地址
  （`t43`）——白名单只放行本实例前缀的**名字**形式，地址形式没法按前缀限定，会
  退回报批。hc 自己的报错提示（`read its screen first (hc read t49)`）会教你用
  地址，别照抄，改成终端名。终端名见 `knowledge/team.md`。
- **图片处理不要直接跑 `sips` / `file`**——两者都不在白名单；`sips` 还能原地改图
  （`-Z` 缩放、`-s format` 另存），比 `echo` 更危险。需要查尺寸或转格式时，先提需求给
  dev 做只读包装器，不要自己找命令绕过。
- **可以用 Skill**：发现到的技能都在权限允许范围内，直接调用即可。技能在不同 CLI 下
  来源不同（claude 看 `.claude/skills/` 与 `~/.claude/skills/`，codex 看 `.agents/skills/`
  与 `~/.agents/skills/`），你要用的技能在当前 CLI 下找不到时，改用等效的手工做法，
  不要反复请求调用权限。
- **只动自己的地盘**：权限层锁住了「写不出实例目录」，但**没有**替你锁住「只写自己
  那几棵子树」——那是你的责任。只写 `roles.json` 里 `scope` 列出的子树与
  `knowledge/work/<角色>/`；`knowledge/business/` 的定稿、`scripts/`、`tools/`
  都归 gm 与 owner，不要直接改（要改就走 gm）。
- **内容区共享但写入受限**：所有角色都能读 `knowledge/content/`；主稿、渠道稿与状态只能
  通过 `tools/opc-workflow` 写，`scope` 只防误写，不提供字段级授权。growth 的指标观测
  同样走 workflow，不直接编辑内容包。

## 记忆注入

角色会话启动时只读**三件套**：

1. **品牌口径**：`knowledge/business/品牌口径.md`；
2. **本角色的经验教训**：`knowledge/work/<角色>/LESSONS.md`；
3. **本次任务的详情**：任务卡（`knowledge/tasks/<task_id>.md`）上的详情与验收。

除此之外一律不读：不读整个业务目录，不读已完成的条目，不读别人的收件箱或任务卡。
这样每个回合的上下文才是可控的。

经验教训**只追加**，写在**本角色**的 `knowledge/work/<角色>/LESSONS.md` 里，格式固定
三行（带日期与角色）；编排者每周汇总到根目录的 `LESSONS.md`。别角色的教训目录不要写，
汇总也不要自己代劳。

## 启动不自主开工

角色启动后**只做三件事**：读规约、读三件套、汇报现状。然后**等 gm 派工**。

- 没有派工到自己的任务卡时：不自选选题、不创建内容卡、不写稿、不改业务口径、
  不修 bug、不写工具、不做实验。没有派工就没有产出。
- 品牌定位、内容支柱、频道选择由 gm 与 owner 对齐后写进 `knowledge/business/品牌口径.md`，
  gm 再往 content 派选题与写稿任务。对齐完成前，content 不开题、不开稿。
- 发现问题先上报 gm（`hc send <前缀>-gm`），修不修、谁修、排在什么位置由 gm 决定；
  角色不要自己动手修自己没被派工的事。
- gm 的启动顺序也不同：先与 owner 对齐方向（品牌定位、内容支柱、频道选择），
  再派内容线的工。对齐完成前，gm 只允许派**不依赖口径的维护类工**
  （工具修复、技术债、方案草案），并在汇报里说明这批工为什么不依赖口径。

## 决策与日志

裁决、阻塞解除、权限缺口等写进 `knowledge/decisions/<YYYY-MM-DD>-<主题>.md`，不再有
每日汇总目录。派工与状态仍只认 `knowledge/tasks/` 下的任务卡：decisions 是日志，
不是待办。格式：

```markdown
# 2026-11-04 · <主题>

## 决定
- <一句话说清决定了什么>

## 理由
- <为什么>

## 影响
- <受影响的角色、内容或 publication>
```

## 项目文档

- Issues 与 specs 使用 GitHub Issues；具体仓库若有额外约定，以实例内可见的规约为准。
- 需要沉淀领域模型时，可按需创建根 `CONTEXT.md`；架构决策放进 `docs/adr/`。
  这些文件只在实例确实需要时创建，不依赖模版仓库外层的开发文档。
