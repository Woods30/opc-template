---
name: opc-workflow
description: 用 tools/opc-workflow 推进内容生命周期：建卡、转态、审批落盘、发布事实、复盘与关闭。
---

# 内容生命周期操作手册

内容事实只有一处真源：`tools/opc-workflow` 写出的 canonical 记录。所有状态变化、
审批决定与发布事实都通过命令落盘，不要靠改文件或搬目录表达状态。

## 固定位置

一条内容从建立起位置就不变：

```text
knowledge/content/<content_id>/
├── 内容卡.md                              # 状态、事件、审批、publication 的唯一记录
├── 主稿.md                                # 固定主稿，不移动、不复制
└── publications/<publication_id>/
    ├── 渠道稿.md                          # 固定渠道稿
    └── assets/                            # 只在某个渠道用的素材
```

- **主稿留在内容包里**：审阅、修改、定稿都改 `<content_id>/主稿.md` 本身，
  不把它复制或搬到 `knowledge/business/`。`business/` 里放的是结果与 generated 视图，
  不是稿件的第二个副本。
- **状态写在记录里**：内容卡上的状态字段与事件链是唯一状态来源。不要用「文件移走了」
  「目录改名了」表达状态变更——那会让记录与磁盘对不上。
- 通用素材放 `<content_id>/assets/`；渠道专属素材放对应 publication 的 `assets/`。

## 命令速查

| 目的 | 命令 |
|---|---|
| 建卡 | `tools/opc-workflow create-content --title "<标题>" [--source "<来源>"] [--target-date YYYY-MM-DD] --actor content` |
| 进入写稿 | `tools/opc-workflow transition <content_id> --to drafting --actor content` |
| 提交审阅 | `tools/opc-workflow transition <content_id> --to reviewing --actor content` |
| 落盘审批决定 | `tools/opc-workflow transition <content_id> --decision <approved\|changes_requested\|rejected> --actor gm [--note "<原因>"]` |
| 建渠道 publication | `tools/opc-workflow create-publication <content_id> --channel <channel> --actor gm [--required-window 48h] [--optional]` |
| 请求渠道稿审阅 | `tools/opc-workflow transition <publication_id> --to reviewing --actor content` |
| 排期 | `tools/opc-workflow transition <publication_id> --to scheduled --planned-at "<ISO 8601>" --timezone <IANA 时区> --actor gm` |
| 落盘发布事实 | `tools/opc-workflow transition <publication_id> --to published --actual-at "<ISO 8601>" --url "<发布 URL>" --actor gm` |
| 记录指标 | `tools/opc-workflow record-metrics <publication_id> --window 48h --observed-at "<ISO 8601>" --source "<来源>" --values '<JSON>' --actor growth` |
| 记录账号级观测 | `tools/opc-workflow record-channel-snapshot --channel <channel> --observed-at "<ISO 8601>" --source "<来源>" --values '<JSON>' --actor growth` |
| 记录阻塞 | `tools/opc-workflow block <content_id> --reason "<原因>" --actor content` |
| 解除阻塞 | `tools/opc-workflow unblock <content_id> [--note "<说明>"] --actor gm` |
| 复盘 | `tools/opc-workflow transition <publication_id> --to reviewed --conclusion <continue\|iterate\|stop\|inconclusive> --next-action "<下一项行动>" --actor growth` |
| 关闭内容 | `tools/opc-workflow transition <content_id> --to closed --actor gm` |
| 作废选题 | `tools/opc-workflow transition <content_id> --to cancelled --note "<原因>" --actor gm` |
| 校验 | `tools/opc-workflow validate` |
| 刷新 generated 视图 | `tools/opc-workflow build` |

一条命令只做一件事：不要用 `;` 或 `&&` 把第二条命令串上去。

## 谁在什么时候动

- **content**：建卡、写稿、提交审阅、请求渠道稿审阅、记录自己发现的阻塞。
- **gm**：落盘 owner 的审批决定、建 publication、排期、落盘发布事实、解除阻塞、
  关闭内容、作废选题。
- **growth**：记录指标与账号级观测、完成 publication 复盘。
- **dev**：不参与内容状态，只保证工具可用。

`--actor` 只能是自己在 `roles.json` 里的 role key（默认取 `OPC_ROLE`）。不得冒充
其他角色记录事实。

## 审批与发布事实

1. 提交审阅时 workflow 把主稿的 SHA-256 写进待审批记录；审批后主稿再被修改，
   审批自动失效（`stale approval`）。改完要重新提交、重新审批，旧决定留在事件链里。
2. 退回与拒绝必须带 `--note`，理由是 owner 的决定，不是执行者的猜测。
3. 只有 valid approved 的稿件能排期，只有 scheduled 的 publication 能确认发布。
4. 发布事实由 owner 实际发布后由 gm 落盘：`--to published --actual-at "<ISO 8601>" --url "<URL>"`。
   计划时间与实际时间分开记录，互不覆盖；published 不能退回发布前状态。
5. 同一内容再次发布要新建 publication，旧记录保持 published，历史与指标归属不丢。

## 阻塞

阻塞不是生命周期状态，是内容卡上的独立对象：

- 记录：只有 gm 与 content 能记。
- 解除：gm 记录的阻塞只有 gm 能解除；content 记录的阻塞 gm 或 content 都能解除。
- 阻塞是硬闸门：受阻内容不能写稿、请求审核、落盘审批、建 publication 或排期。
  先解除或作废，再继续。已发布事实、指标记录与复盘不受阻塞影响。

## 关闭与作废

- 关闭内容要求所有必需 publication 已 reviewed 或已带原因 cancelled；命令失败时会列出
  阻塞项。可选 publication（`--optional`）不阻塞关闭。
- 必需指标窗口确实拿不到数据时，由 gm 带 `--exception-reason` 落盘例外，例外进事件链。
- 作废只对 proposed 或 drafting 开放，是终态：取消原因留在内容卡上，不要另建一张表记这件事。

## 排错

- 命令被拒且提示状态不对：先跑 `tools/opc-workflow validate`，看内容卡与事件链。
- `stale approval`：主稿在审批后被改过，重新提交并重新审批。
- 看板或日历里的状态不对：跑 `tools/opc-workflow build` 刷新 generated 视图，
  不要手工编辑 `knowledge/business/选题日历.md`、频道 `发布记录.md` 与 `dashboard.json`。
- 需要 owner 的决定才能推进：写进 `knowledge/decisions/`，由 gm 落盘决定。
