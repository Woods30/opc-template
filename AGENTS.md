# OPC 公司共享规约

本文件是 **OPC 各角色 agent 的统一入口**。默认角色是 gm / content / growth / dev，
但角色是配置：以 `roles.json` 为准，当前启用了哪些、各自终端名叫什么，见
`knowledge/team.md`。`CLAUDE.md` 转发到这里；角色专属的职责与边界写在各自模板
正文里，不在此重复。

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
│   ├── 选题日历.md
│   └── dashboard.json  # generated 只读视图：看板 JSON 契约（build 生成）
├── decisions/    # 决策记录（gm 裁决后落盘）
├── inbox/        # 任务投递：gm.md / content.md / growth.md / dev.md
└── work/<角色>/  # 过程：草稿、提案、实验记录、LESSONS.md
    └── template-proposals/  # 给模版提的改进提案（见「模版与实例」）
```

- `content/` 是**事实**：每条内容从 proposed 起固定在 `<content_id>/内容卡.md`，不靠移动目录表达状态。
  主稿固定在 `<content_id>/主稿.md`，渠道稿固定在
  `<content_id>/publications/<publication_id>/渠道稿.md`。
- `business/` 是**结果与视图**：成稿、常驻口径，以及 generated 只读视图。老板只看这里。
  频道目录只放 generated 发布记录，不放稿件或资产副本。
- `work/` 是**过程**：草稿、提案、日志。老板不看，但进版本库。
- 不再有 `review/` 与 `daily/`：审核状态写在 canonical 记录里，决策写 `decisions/`。

命名规则：**目录是结构，用英文；文件是内容，用中文**。目录一律小写 ASCII slug。

`knowledge/` 是唯一的事实来源。**结论必须落盘**，聊天与终端里的内容不算数。

## 模版与实例

OPC 有两层：**模版**（通用机制，公开仓库）与**实例**（这一家的真实业务，本地仓库）。
角色在**实例**里运行，模版只装机制。

- 模版里的占位骨架在 `seeds/business/`，开实例时物化到本目录的
  `knowledge/business/`。物化之后通常归业务所有；标有 `GENERATED FILE — READ ONLY`
  的文件例外，只能通过对应生成命令刷新。
- **发现模版要改，不要在实例里直接改模版文件**（脚本、简报、规约）。改实例的
  副本会在下一次同步时被覆盖，而且会把模版和业务的改动搅在一起。
- 正确做法是写**提案**：`knowledge/work/<角色>/template-proposals/<YYYY-MM-DD>-<主题>.md`，
  五个固定小节——`## 现象`、`## 泛化需求`、`## 期望模版改动`、`## 影响文件`、
  `## 脱敏自检`。任何角色都能提，不必等 dev。
- **脱敏是硬要求**：提案里只讲机制与流程，不出现真实品牌名、真实频道 id
  （wechat/x/zhihu…）、真实数字指标。要举例就用 `<占位>`。
- 提案先由 gm 汇总进 `knowledge/decisions/`，owner 脱敏后人工搬进模版仓库。
- `scripts/` 与 `tools/` 是执行面，只有 owner 能改；角色改不了，也不要绕。

## 协作协议

### 派工

发起方把任务**追加**到 `knowledge/inbox/<角色名>.md`，每条一行，格式：

```
- [2026-11-04 09:30] 发起方：gm | 任务 ID：task-a1b2c3d4e5f6 | 业务引用：<content_id 或 publication_id> | 任务：产出本周选题清单 | 验收：10 个选题，各含标题与一句话钩子
```

- **`knowledge/inbox/` 只有 gm 可写**。其他角色只能通过 `hc send` 上报，由 gm 落盘。
- `任务 ID` 形如 `task-<小写字母数字>`，由 gm 分配且全实例唯一；后续改措辞、补验收时
  保持不变。没写时 workflow 会按「角色 + 时间 + 任务文本」派生一个稳定 ID。
- `业务引用` 指向这条任务服务的 canonical 记录（content_id / publication_id），没有就写
  `-`；看板用它把任务与内容、发布连起来。

追加完成后通知对方：

```sh
hc send <前缀>-<角色名> "任务已投递：见 knowledge/inbox/<角色名>.md 最新一条"
```

`<前缀>` 是本实例的项目前缀，`knowledge/team.md` 里有准确名字——**发消息前先查名册**，
不要凭记忆拼终端名。

### 执行

收到通知后读 `knowledge/inbox/<角色名>.md` 的最新条目执行。产出分三种：

- **过程**（草稿、提案、实验记录）写 `knowledge/work/<角色名>/`；
- **内容事实**通过 `tools/opc-workflow` 写入 `knowledge/content/<content_id>/`；
- **常驻表**（`business/品牌口径.md`、`business/growth/指标.md` 等）由所属角色直接维护。

`knowledge/business/选题日历.md` 是 generated 只读视图；运行 `tools/opc-workflow build`
从内容卡刷新，不得手工编辑。日历分两节：**待排期选题**放没有目标日期的活跃内容，
**已排期内容**放有目标日期的活跃内容；已关闭与已取消的内容是历史，不进日历，
去内容卡或看板历史里看。内容卡里的 actor 只能是自己的 role key（默认取
`OPC_ROLE`），不得冒充其他角色。

完成后回报：

```sh
hc send <前缀>-<发起方> "完成：<产出文件路径>"
```

### 状态来源（动手前先读这条）

`inbox/` 是**队列**，`decisions/` 是**日志**。两者不能混着当待办读：

- **只有 `inbox/<角色>.md` 里未标记的条目是可执行待办。**
- `decisions/`、`work/` 里的历史描述**一律不作为「现在该做什么」的依据**。
  它们记录的是当时的状态，可能早已被推翻。
- 状态变化必须写回**派工所在的那个 inbox 条目**，不能只写进决策文档：
  - 发起方收到「完成」回报后，在该条目行首加 `✅`；
  - 任务撤销时，在该条目行首加 `⛔ 已撤销：<一句话原因>`；
  - 角色只执行行首既无 `✅` 也无 `⛔` 的条目。
- 因此：**新 session 启动后，第一件事是读自己 inbox 里未标记的条目**，不要从
  `decisions/` 反推任务。看到两份文件说法不一致，以 inbox 为准，并向 gm 报告。

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
2. 看板是独立的 herdr mod（`mods/opc-dashboard/`），只读这份 JSON，不遍历也不解析
   canonical Markdown，也不承担任何业务写入——canonical 记录的写入仍然只有 workflow
   命令；看板最多重跑一次 `build` 刷新 generated 视图。
3. 看板默认视图聚焦未关闭或受阻内容、待审批、开放任务，以及未完成指标/复盘、近期发布
   与近期计划的 publication；历史默认不计入，避免旧数据污染 KPI。
4. 看板点条目时只读预览对应的 canonical 源文件；点角色时按 `knowledge/team.md` 里的
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

   **不要直接写 `knowledge/inbox/gm.md`**——`knowledge/inbox/` 只有 gm 可写，
   其他角色写它会被直接拒绝。由 gm 收到后代为落盘。

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
说明情况（终端名见 `knowledge/team.md`），由 gm 决定并落盘到 `knowledge/inbox/gm.md`
——**`knowledge/inbox/` 只有 gm 可写**，其他角色直接写会被拒。

### 消息格式

- 短句，先结论后细节。
- 一次只说一件事。
- 引用文件路径，不要粘贴长内容。
- 收到的消息带 `<hc from="t1x opc-content">` 标签，这是 hc 的通知格式，忽略标签本身即可。

### 角色终端名

每个角色是一个 `hc` 终端，名字格式为 `<项目前缀>-<角色>`（例如项目 `opc` 下的
`opc-gm`）。**当前实例的完整名册在 `knowledge/team.md`**，那是唯一权威来源——
`hc send` 要用准确的名字，用之前先查它。

终端内 `$HC_TERMINAL_ID` 是自己的地址，可用于自报家门。`hc ls` 列出全部 live 终端。

## 通用工作约定

- **先读后写**：动手前先读相关文件，不凭猜测改文件。
- **产出落盘**：过程写 `knowledge/work/<角色>/`，最终产出由 gm 搬进 `knowledge/business/`；
  命名带日期，如 `2026-11-04-选题清单.md`。
- **不越权**：不擅自发布对外内容、不擅自承诺预算、不擅自改业务优先级、不擅自对外承诺。
- **遇到问题上报**，而不是硬扛或自行拍板。
- **不启动子 agent**，除非 gm 明确指派。
- **不修改本文件与 `CLAUDE.md`**；规约变更由 gm 决定。
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

## 决策与日志

裁决、阻塞解除、权限缺口等写进 `knowledge/decisions/<YYYY-MM-DD>-<主题>.md`，不再有
每日汇总目录。派工与状态仍只认 `knowledge/inbox/`：decisions 是日志，不是待办。格式：

```markdown
# 2026-11-04 · <主题>

## 决定
- <一句话说清决定了什么>

## 理由
- <为什么>

## 影响
- <受影响的角色、内容或 publication>
```
