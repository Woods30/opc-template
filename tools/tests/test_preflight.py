#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/preflight 的测试。标准库 unittest，不依赖外部包。

测试 fixture 全部使用 canonical 内容与 publication 模型：
内容卡 + 主稿，或发布卡 + 渠道稿。选题日历不参与，也不创建。

跑法：
    python3 -m unittest discover -s tools/tests -t . -v
"""

import hashlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PREFLIGHT = os.path.join(ROOT, "tools", "preflight")

CONTENT_ID = "content-20261104-120000000000-aaaaaaaa"
PUBLICATION_ID = "publication-20261104-130000000000-bbbbbbbb"
X_PUBLICATION_ID = "publication-20261104-140000000000-cccccccc"


def load_module():
    # 不生成 __pycache__：tools/ 目录不留构建产物
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_loader(
        "preflight",
        importlib.machinery.SourceFileLoader("preflight", PREFLIGHT),
    )
    module = importlib.util.module_from_spec(spec)
    # dataclass 装饰器会回查 sys.modules 里的模块对象，先登记再执行
    sys.modules["preflight"] = module
    spec.loader.exec_module(module)
    return module


pf = load_module()

BRAND = """# 品牌口径

## 语气

- 专业但不端着。

## 作者人设

- 第一人称用「我」，**不称「我们」**，不冒充团队。
- 【提案】可公开：我在做什么。

## 渠道口径

**主渠道：公众号**（2026-11-04 owner 与 gm 双确认）。只做深这一个渠道。

| 渠道 | 角色 | 形态要求 | 字数口径 | CTA 口径 |
|---|---|---|---|---|
| 公众号 | 主渠道 | 长文 | 1800～3000 字 | 关注公众号；不得出现 链接、二维码、邮箱 |
| 知乎 | 改写 | 问答体 | 1500～2500 字 | 关注公众号 |
| X | 改写 | 单条或 thread | 单条 ≤200 字；thread 每条 ≤140 字 | 关注公众号 |

## 术语表

| 我们说什么 | 不说什么 | 说明 |
|---|---|---|
| 一人公司 | 个体户、小微创业 | OPC |
| AI 角色 | 取代团队、无人公司 | 是分工 |
| 主渠道 | 全渠道铺开 | 先做深一个 |

## 禁用表述

- 不承诺未验证的效果。
- 不说「全自动」「无人值守」「躺赚」。
- 不把「正在做」说成「已经做到」，不把单个案例说成普遍规律。
"""

GOOD_DRAFT = """# 第一篇

> **渠道**：公众号（主稿）

正文写得很具体，给数字，给例子。

关注公众号，后续更新第一时间看到。
"""

X_DRAFT = """# 第一篇（X 短帖改写）

> **渠道**：X（改写稿）

短帖正文。

关注公众号。
"""

ZHIHU_DRAFT = """# 第一篇（知乎问答改写）

> **渠道**：知乎（问答体）

问答正文。

关注公众号。
"""


def artifact_hash(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


class PreflightTestCase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="preflight-test-")
        business_dir = os.path.join(self.root, "knowledge", "business")
        os.makedirs(business_dir)
        self.business_dir = business_dir
        self.write(os.path.join(business_dir, "品牌口径.md"), BRAND)
        self.write(
            os.path.join(self.root, "channels.json"),
            json.dumps(
                {
                    "channels": [
                        {"id": "wechat", "name": "公众号", "enabled": True},
                        {"id": "zhihu", "name": "知乎", "enabled": True},
                        {"id": "x", "name": "X", "enabled": True},
                    ]
                },
                ensure_ascii=False,
            ),
        )

        self.content_dir = os.path.join(
            self.root, "knowledge", "content", CONTENT_ID
        )
        os.makedirs(self.content_dir)
        self.main_draft = os.path.join(self.content_dir, "主稿.md")
        self.content_card = os.path.join(self.content_dir, "内容卡.md")
        self.write(self.main_draft, GOOD_DRAFT)
        self.write_content_card()

        self.publication_dir = os.path.join(
            self.content_dir, "publications", PUBLICATION_ID
        )
        os.makedirs(self.publication_dir)
        self.zhihu_draft = os.path.join(self.publication_dir, "渠道稿.md")
        self.publication_card = os.path.join(self.publication_dir, "发布卡.md")
        self.write(self.zhihu_draft, ZHIHU_DRAFT)
        self.write_publication_card()

        self.x_publication_dir = os.path.join(
            self.content_dir, "publications", X_PUBLICATION_ID
        )
        os.makedirs(self.x_publication_dir)
        self.x_draft = os.path.join(self.x_publication_dir, "渠道稿.md")
        self.write(self.x_draft, X_DRAFT)
        self.write_publication_card(
            publication_id=X_PUBLICATION_ID,
            channel="x",
            title="第一篇（X 短帖改写）",
        )

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, path, text):
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)

    def write_card(self, path, record, body):
        payload = json.dumps(record, ensure_ascii=False, indent=2)
        self.write(path, "---\n{}\n---\n{}".format(payload, body))

    def approval(self, artifact, draft_path):
        return {
            "status": "approved",
            "requested_at": "2026-11-04T12:00:00+08:00",
            "requested_by": "content",
            "artifact": artifact,
            "artifact_hash": artifact_hash(draft_path),
            "decided_at": "2026-11-04T12:30:00+08:00",
            "decided_by": "gm",
        }

    def write_content_card(self):
        record = {
            "schema_version": 1,
            "record_type": "content",
            "content_id": CONTENT_ID,
            "title": "第一篇",
            "status": "ready",
            "created_at": "2026-11-04T11:00:00+08:00",
            "actor": "content",
            "main_draft": "主稿.md",
            "pillar": "AI 角色",
            "approval": self.approval("主稿.md", self.main_draft),
            "events": [
                {
                    "action": "create",
                    "at": "2026-11-04T11:00:00+08:00",
                    "actor": "content",
                    "to_status": "proposed",
                }
            ],
        }
        self.write_card(self.content_card, record, "\n# 内容卡\n")

    def write_publication_card(
        self, publication_id=PUBLICATION_ID, channel="zhihu", title="第一篇（知乎问答改写）"
    ):
        package = os.path.join(self.content_dir, "publications", publication_id)
        draft_name = "渠道稿.md"
        card = os.path.join(package, "发布卡.md")
        record = {
            "schema_version": 1,
            "record_type": "publication",
            "publication_id": publication_id,
            "content_id": CONTENT_ID,
            "channel": channel,
            "title": title,
            "status": "reviewing",
            "created_at": "2026-11-04T13:00:00+08:00",
            "actor": "gm",
            "channel_draft": draft_name,
            "approval": self.approval(draft_name, os.path.join(package, draft_name)),
            "events": [
                {
                    "action": "create",
                    "at": "2026-11-04T13:00:00+08:00",
                    "actor": "gm",
                    "to_status": "adapting",
                }
            ],
        }
        self.write_card(card, record, "\n# 发布卡\n")

    def check_by_id(self, checks, check_id):
        for check in checks:
            if check.id == check_id:
                return check
        self.fail("没有找到检查项 {}".format(check_id))

    def run_main(self, channel=None):
        return pf.run_checks(self.root, self.main_draft, channel)

    def run_publication(self, publication_id=PUBLICATION_ID, channel=None):
        return pf.run_checks(
            self.root,
            None,
            channel,
            content_id=CONTENT_ID,
            publication_id=publication_id,
        )

    # ---------- 禁用词抽取 ----------

    def test_forbidden_terms_include_table_and_quote_terms(self):
        terms, table_terms, other_terms = pf.forbidden_terms(BRAND)
        for expected in ("个体户", "小微创业", "取代团队", "无人公司", "全渠道铺开"):
            self.assertIn(expected, table_terms, "术语表禁用词里应有 {}".format(expected))
        for expected in ("全自动", "无人值守", "躺赚", "我们"):
            self.assertIn(expected, other_terms, "口径禁用词里应有 {}".format(expected))
        self.assertEqual(sorted(terms), sorted(table_terms + other_terms))

    def test_not_put_as_only_bans_the_target_phrase(self):
        _, _, other_terms = pf.forbidden_terms(BRAND)
        self.assertIn("已经做到", other_terms)
        self.assertNotIn("正在做", other_terms, "「不把A说成B」里 A 可以写，只禁 B")

    def test_first_person_pronoun_not_banned(self):
        _, _, other_terms = pf.forbidden_terms(BRAND)
        self.assertNotIn("我", other_terms, "「用「我」」不是说不用「我」，只有「不称X」才禁")

    def test_brand_header_row_is_not_treated_as_term(self):
        _, table_terms, _ = pf.forbidden_terms(BRAND)
        self.assertNotIn("不说什么", table_terms)
        self.assertNotIn("说明", table_terms)

    # ---------- canonical 解析 ----------

    def test_clean_main_draft_passes_all_hard_checks(self):
        checks = self.run_main()
        failed = [c.id for c in checks if c.status == pf.STATUS_FAIL]
        self.assertEqual(failed, [], "干净稿件不该有失败项：{}".format(failed))
        self.assertEqual(
            self.check_by_id(checks, "content-record").status, pf.STATUS_OK
        )
        self.assertEqual(
            self.check_by_id(checks, "approval-valid").status, pf.STATUS_OK
        )

    def test_publication_draft_resolves_canonical_record_by_id(self):
        checks = pf.run_checks(
            self.root, None, None, publication_id=PUBLICATION_ID
        )
        failed = [c.id for c in checks if c.status == pf.STATUS_FAIL]
        self.assertEqual(failed, [], "干净渠道稿不该有失败项：{}".format(failed))
        record = self.check_by_id(checks, "publication-record")
        self.assertEqual(record.status, pf.STATUS_OK)
        self.assertTrue(any(PUBLICATION_ID in item for item in record.detail))
        self.assertEqual(
            self.check_by_id(checks, "channel-match").status, pf.STATUS_OK
        )

    def test_content_shortcut_points_at_main_draft(self):
        checks = pf.run_checks(self.root, content_id=CONTENT_ID)
        self.assertEqual(self.check_by_id(checks, "draft-exists").status, pf.STATUS_OK)
        self.assertEqual(self.check_by_id(checks, "content-record").status, pf.STATUS_OK)

    def test_legacy_channel_layout_is_rejected(self):
        legacy = os.path.join(self.business_dir, "wechat", "2026-11-04-第一篇.md")
        os.makedirs(os.path.dirname(legacy))
        self.write(legacy, GOOD_DRAFT)
        checks = pf.run_checks(self.root, legacy)
        location = self.check_by_id(checks, "draft-location")
        self.assertEqual(location.status, pf.STATUS_FAIL)
        self.assertTrue(any("canonical" in item for item in location.detail))

    def test_missing_content_card_is_located(self):
        os.remove(self.content_card)
        checks = self.run_main()
        content = self.check_by_id(checks, "content-record")
        self.assertEqual(content.status, pf.STATUS_FAIL)
        self.assertTrue(any("内容卡" in item for item in content.detail))
        self.assertEqual(
            self.check_by_id(checks, "approval-valid").status, pf.STATUS_SKIP
        )

    def test_broken_publication_reference_is_located(self):
        with open(self.publication_card, encoding="utf-8") as handle:
            text = handle.read()
        record = json.loads(text.split("---\n")[1])
        record["content_id"] = "content-20261104-120000000000-dddddddd"
        self.write_card(
            self.publication_card, record, text.split("---\n")[2]
        )

        checks = self.run_publication()
        publication = self.check_by_id(checks, "publication-record")
        self.assertEqual(publication.status, pf.STATUS_FAIL)
        self.assertTrue(any("引用断裂" in item for item in publication.detail))

    def test_publication_missing_from_disk_is_located(self):
        missing = "publication-20261104-130000000000-ffffffff"
        checks = pf.run_checks(self.root, None, None, publication_id=missing)
        publication = self.check_by_id(checks, "publication-record")
        self.assertEqual(publication.status, pf.STATUS_FAIL)
        self.assertTrue(any(missing in item for item in publication.detail))

    # ---------- 审批 ----------

    def test_stale_approval_fails(self):
        self.write(self.main_draft, GOOD_DRAFT + "\n审批后又加了一段。\n")
        checks = self.run_main()
        approval = self.check_by_id(checks, "approval-valid")
        self.assertEqual(approval.status, pf.STATUS_FAIL)
        self.assertTrue(any("审批失效" in item for item in approval.detail))

    def test_pending_approval_fails(self):
        with open(self.content_card, encoding="utf-8") as handle:
            text = handle.read()
        card = json.loads(text.split("---\n")[1])
        card["approval"]["status"] = "pending"
        self.write_card(self.content_card, card, text.split("---\n")[2])

        checks = self.run_main()
        approval = self.check_by_id(checks, "approval-valid")
        self.assertEqual(approval.status, pf.STATUS_FAIL)
        self.assertTrue(any("pending" in item for item in approval.detail))

    def test_publication_draft_approval_is_checked(self):
        self.write(self.zhihu_draft, ZHIHU_DRAFT + "\n审批后改稿。\n")
        checks = self.run_publication()
        approval = self.check_by_id(checks, "approval-valid")
        self.assertEqual(approval.status, pf.STATUS_FAIL)
        self.assertTrue(any("渠道稿.md" in item for item in approval.detail))

    def test_cancelled_publication_is_not_publishable(self):
        with open(self.publication_card, encoding="utf-8") as handle:
            text = handle.read()
        card = json.loads(text.split("---\n")[1])
        card["status"] = "cancelled"
        self.write_card(self.publication_card, card, text.split("---\n")[2])

        checks = self.run_publication()
        approval = self.check_by_id(checks, "approval-valid")
        self.assertEqual(approval.status, pf.STATUS_FAIL)
        self.assertTrue(any("cancelled" in item for item in approval.detail))

    # ---------- 路径安全 ----------

    def test_symlinked_draft_is_rejected(self):
        outside_dir = tempfile.mkdtemp(prefix="preflight-outside-")
        self.addCleanup(shutil.rmtree, outside_dir, True)
        outside = os.path.join(outside_dir, "outside.md")
        self.write(outside, GOOD_DRAFT)
        os.remove(self.main_draft)
        os.symlink(outside, self.main_draft)

        checks = self.run_main()
        location = self.check_by_id(checks, "draft-location")
        self.assertEqual(location.status, pf.STATUS_FAIL)
        self.assertTrue(any("symlink" in item for item in location.detail))

    def test_symlinked_content_card_is_rejected(self):
        outside_dir = tempfile.mkdtemp(prefix="preflight-outside-")
        self.addCleanup(shutil.rmtree, outside_dir, True)
        outside = os.path.join(outside_dir, "内容卡.md")
        self.write(outside, json.dumps({"record_type": "content"}))
        os.remove(self.content_card)
        os.symlink(outside, self.content_card)

        checks = self.run_main()
        content = self.check_by_id(checks, "content-record")
        self.assertEqual(content.status, pf.STATUS_FAIL)
        self.assertTrue(any("symlink" in item for item in content.detail))

    def test_publication_directory_outside_root_is_rejected(self):
        outside_dir = tempfile.mkdtemp(prefix="preflight-outside-")
        self.addCleanup(shutil.rmtree, outside_dir, True)
        moved = os.path.join(outside_dir, PUBLICATION_ID)
        shutil.move(self.publication_dir, moved)
        os.symlink(moved, self.publication_dir)

        checks = self.run_publication()
        publication = self.check_by_id(checks, "publication-record")
        self.assertEqual(publication.status, pf.STATUS_FAIL)
        self.assertTrue(
            any("symlink" in item or "越出实例目录" in item for item in publication.detail)
        )

    # ---------- 渠道 ----------

    def test_channel_mismatch_fails(self):
        self.write(self.zhihu_draft, ZHIHU_DRAFT.replace("知乎（问答体）", "公众号"))
        checks = self.run_publication()
        check = self.check_by_id(checks, "channel-match")
        self.assertEqual(check.status, pf.STATUS_FAIL)
        self.assertTrue(any("知乎" in item for item in check.detail))

    def test_channel_match_ignores_parenthetical(self):
        checks = self.run_publication(X_PUBLICATION_ID)
        self.assertEqual(self.check_by_id(checks, "channel-match").status, pf.STATUS_OK)

    def test_unlabelled_draft_is_a_warning(self):
        self.write(self.main_draft, "# 第一篇\n\n正文。\n\n关注公众号。\n")
        checks = self.run_main()
        check = self.check_by_id(checks, "channel-match")
        self.assertEqual(check.status, pf.STATUS_WARN)
        self.assertTrue(any("未标注渠道" in item for item in check.detail))

    def test_missing_brand_main_channel_is_a_warning(self):
        brand_path = os.path.join(self.business_dir, "品牌口径.md")
        with open(brand_path, encoding="utf-8") as handle:
            text = handle.read()
        self.write(brand_path, text.replace("**主渠道：公众号**", "**主渠道：待定**")
                   .replace("主渠道：公众号", "主渠道：待定"))
        checks = self.run_main()
        check = self.check_by_id(checks, "channel-match")
        self.assertEqual(check.status, pf.STATUS_WARN)
        self.assertTrue(any("主渠道" in item for item in check.detail))

    # ---------- 品牌检查 ----------

    def test_forbidden_word_fails(self):
        self.write(self.main_draft, GOOD_DRAFT + "\n我们把躺赚写进正文。\n")
        checks = self.run_main()
        check = self.check_by_id(checks, "forbidden-term")
        self.assertEqual(check.status, pf.STATUS_FAIL)
        self.assertTrue(any("躺赚" in d for d in check.detail))

    def test_term_table_misuse_fails(self):
        self.write(self.main_draft, GOOD_DRAFT + "\n我们是小微创业。\n")
        checks = self.run_main()
        check = self.check_by_id(checks, "term-misuse")
        self.assertEqual(check.status, pf.STATUS_FAIL)
        self.assertTrue(any("小微创业" in d for d in check.detail))

    def test_we_char_counts_as_forbidden(self):
        self.write(self.main_draft, GOOD_DRAFT + "\n我们想看看。\n")
        checks = self.run_main()
        self.assertEqual(self.check_by_id(checks, "forbidden-term").status, pf.STATUS_FAIL)

    def test_fenced_code_is_skipped(self):
        self.write(self.main_draft, GOOD_DRAFT + "\n```\n躺赚\n```\n")
        checks = self.run_main()
        self.assertEqual(self.check_by_id(checks, "forbidden-term").status, pf.STATUS_OK)

    def test_brand_proposal_marker_is_warning_only(self):
        checks = self.run_main()
        check = self.check_by_id(checks, "brand-settled")
        self.assertEqual(check.status, pf.STATUS_WARN)

    def test_content_pillar_present(self):
        checks = self.run_main()
        check = self.check_by_id(checks, "content-pillar")
        self.assertEqual(check.status, pf.STATUS_OK)
        self.assertTrue(any("AI 角色" in item for item in check.detail))

    def test_content_pillar_missing_is_warning(self):
        with open(self.content_card, encoding="utf-8") as handle:
            text = handle.read()
        card = json.loads(text.split("---\n")[1])
        card.pop("pillar", None)
        self.write_card(self.content_card, card, text.split("---\n")[2])
        checks = self.run_main()
        self.assertEqual(
            self.check_by_id(checks, "content-pillar").status, pf.STATUS_WARN
        )

    # ---------- 文件 ----------

    def test_missing_draft_is_reported_not_crashed(self):
        os.remove(self.main_draft)
        checks = self.run_main()
        self.assertEqual(self.check_by_id(checks, "draft-exists").status, pf.STATUS_FAIL)

    def test_missing_draft_path_is_located(self):
        missing = os.path.join(
            self.root,
            "knowledge",
            "content",
            "content-20261104-120000000000-dddddddd",
            "主稿.md",
        )
        checks = pf.run_checks(self.root, missing)
        self.assertEqual(self.check_by_id(checks, "draft-exists").status, pf.STATUS_FAIL)
        self.assertEqual(
            self.check_by_id(checks, "content-record").status, pf.STATUS_FAIL
        )

    def test_generated_calendar_is_ignored(self):
        # preflight 不再读选题日历：就算它写着相反的内容也不影响结论
        calendar = os.path.join(self.business_dir, "选题日历.md")
        self.write(
            calendar,
            "# 选题日历\n\n> **GENERATED FILE — READ ONLY**\n\n| 选题 | 稿件路径 |\n|---|---|\n",
        )
        checks = self.run_main()
        failed = [c.id for c in checks if c.status == pf.STATUS_FAIL]
        self.assertEqual(failed, [])
        self.assertIsNone(
            next((c for c in checks if c.id == "calendar-entry"), None),
            "canonical 模型下不应再有 calendar-entry 检查",
        )

    # ---------- 退出码 ----------

    def test_exit_code_zero_on_clean_draft(self):
        code = pf.main([self.main_draft, "--root", self.root])
        self.assertEqual(code, 0)

    def test_exit_code_zero_with_publication_selector(self):
        code = pf.main(
            ["--publication", PUBLICATION_ID, "--root", self.root]
        )
        self.assertEqual(code, 0)

    def test_exit_code_nonzero_on_failure(self):
        self.write(self.main_draft, GOOD_DRAFT + "\n躺赚。\n")
        code = pf.main([self.main_draft, "--root", self.root])
        self.assertEqual(code, 1)

    def test_exit_code_two_on_missing_file(self):
        code = pf.main(
            [os.path.join(self.root, "不存在.md"), "--root", self.root]
        )
        self.assertEqual(code, 2)

    # ---------- 字数 / CTA ----------

    def test_word_count_ignores_code_blocks(self):
        self.assertEqual(pf.word_count("你好\n```\n代码\n```\n世界"), 4)

    def test_x_draft_word_count_checked_per_block(self):
        self.write(
            self.x_draft,
            "# 第一篇（X 短帖改写）\n\n> **渠道**：X（改写稿）\n\n"
            "## 版本 A：单条帖（首发，≤200 字）\n\n" + "字" * 250 + "\n\n"
            "## 版本 B：thread（3 条，每条 ≤140 字）\n\n短。\n",
        )
        checks = self.run_publication(X_PUBLICATION_ID)
        check = self.check_by_id(checks, "word-count")
        self.assertEqual(check.status, pf.STATUS_WARN)
        self.assertTrue(any("250 字" in d for d in check.detail))

    def test_cta_missing_required_phrase_fails(self):
        self.write(
            self.main_draft,
            "# 第一篇\n\n> **渠道**：公众号（主稿）\n\n正文。\n\n看完记得点赞。\n",
        )
        checks = self.run_main()
        check = self.check_by_id(checks, "cta-consistency")
        self.assertEqual(check.status, pf.STATUS_FAIL)
        self.assertTrue(any("关注公众号" in d for d in check.detail))

    def test_cta_forbidden_word_fails(self):
        self.write(self.main_draft, GOOD_DRAFT + "\n关注公众号，或者扫二维码。\n")
        checks = self.run_main()
        check = self.check_by_id(checks, "cta-consistency")
        self.assertEqual(check.status, pf.STATUS_FAIL)
        self.assertTrue(any("二维码" in d for d in check.detail))

    def test_cta_present_passes(self):
        self.write(self.main_draft, GOOD_DRAFT + "\n关注公众号，后续更新第一时间看到。\n")
        checks = self.run_main()
        self.assertEqual(self.check_by_id(checks, "cta-consistency").status, pf.STATUS_OK)

    def test_cta_check_warns_when_spec_column_missing(self):
        brand_path = os.path.join(self.business_dir, "品牌口径.md")
        with open(brand_path, encoding="utf-8") as handle:
            text = handle.read()
        text = text.replace(" | CTA 口径 |", " |").replace(
            " | 关注公众号；不得出现 链接、二维码、邮箱 |", " |"
        )
        self.write(brand_path, text)
        checks = self.run_main()
        check = self.check_by_id(checks, "cta-consistency")
        self.assertEqual(check.status, pf.STATUS_WARN)
        self.assertTrue(any("CTA 口径列" in d for d in check.detail))

    def test_cta_uses_channel_specific_spec(self):
        checks = self.run_publication()
        check = self.check_by_id(checks, "cta-consistency")
        self.assertIn(check.status, (pf.STATUS_OK, pf.STATUS_FAIL))
        self.assertTrue(any("关注公众号" in item for item in check.detail))

    def test_source_files_not_modified(self):
        brand_path = os.path.join(self.business_dir, "品牌口径.md")
        before = os.stat(brand_path).st_mtime_ns
        with open(brand_path, encoding="utf-8") as handle:
            content_before = handle.read()
        self.run_main()
        with open(brand_path, encoding="utf-8") as handle:
            content_after = handle.read()
        self.assertEqual(content_before, content_after)
        self.assertEqual(before, os.stat(brand_path).st_mtime_ns)


class RealRepoRegressionTests(unittest.TestCase):
    """用仓库里真实的品牌口径跑整条 run_checks。

    回归用例：2026-11-04 12:34 版本里 ``forbidden_terms`` 被同名函数覆盖，
    ``run_checks`` 解包失败，所有稿件直接崩溃。只测抽取函数抓不到这类问题，
    必须从 run_checks 入口跑一遍。
    """

    def test_run_checks_on_real_brand_with_cta_column(self):
        brand = os.path.join(ROOT, "knowledge", "business", "品牌口径.md")
        if not os.path.exists(brand):
            self.skipTest("真实仓库品牌口径不存在：{}".format(brand))

        root = tempfile.mkdtemp(prefix="preflight-real-")
        try:
            business_dir = os.path.join(root, "knowledge", "business")
            os.makedirs(business_dir)
            shutil.copyfile(brand, os.path.join(business_dir, "品牌口径.md"))

            content_dir = os.path.join(root, "knowledge", "content", CONTENT_ID)
            os.makedirs(content_dir)
            draft_path = os.path.join(content_dir, "主稿.md")
            with open(draft_path, "w", encoding="utf-8") as handle:
                handle.write(GOOD_DRAFT)
            record = {
                "schema_version": 1,
                "record_type": "content",
                "content_id": CONTENT_ID,
                "title": "第一篇",
                "status": "ready",
                "created_at": "2026-11-04T11:00:00+08:00",
                "actor": "content",
                "approval": {
                    "status": "approved",
                    "requested_at": "2026-11-04T12:00:00+08:00",
                    "requested_by": "content",
                    "artifact": "主稿.md",
                    "artifact_hash": artifact_hash(draft_path),
                    "decided_at": "2026-11-04T12:30:00+08:00",
                    "decided_by": "gm",
                },
                "events": [],
            }
            card = os.path.join(content_dir, "内容卡.md")
            with open(card, "w", encoding="utf-8") as handle:
                handle.write(
                    "---\n{}\n---\n\n# 内容卡\n".format(
                        json.dumps(record, ensure_ascii=False, indent=2)
                    )
                )

            checks = pf.run_checks(root, draft_path)
            self.assertTrue(checks)
            by_id = {check.id: check for check in checks}
            self.assertIn("cta-consistency", by_id)
            # 品牌口径已有 CTA 列，检查必须真正参与判定，而不是回退成「口径未补齐」警告
            self.assertIn(
                by_id["cta-consistency"].status, (pf.STATUS_OK, pf.STATUS_FAIL)
            )

            with open(brand, encoding="utf-8") as handle:
                brand_text = handle.read()
            terms, table_terms, other_terms = pf.forbidden_terms(brand_text)
            self.assertTrue(table_terms, "术语表应抽出禁用语")
            self.assertIsInstance(terms, list)
            self.assertIsInstance(other_terms, list)
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
