#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/preflight 的测试。标准库 unittest，不依赖外部包。

跑法：
    python3 -m unittest discover -s tools/tests -t . -v
"""

import importlib.util
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PREFLIGHT = os.path.join(ROOT, "tools", "preflight")


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

CALENDAR = """# 选题日历

## 主渠道与节奏

- **主渠道：公众号**（owner 与 gm 双确认）。
- **发布节奏：每周 1 篇长文 + 每周 1 次改写分发**。

## 选题（公众号主稿）

| 写稿日 | 计划发布日 | 支柱 | 选题 | 一句话钩子 | 状态 | 稿件路径 | 备注 |
|---|---|---|---|---|---|---|---|
| 11-04 | 11-13 | 1 | 第一篇 | 钩子一 | 待审 | `2026-11-04-第一篇.md` | `utm_campaign=first` |
| 11-05 | 11-20 | 2 | 还没写 | 钩子二 | 待写 | — | — |

## 改写排期（不是新选题）

| 改写源（公众号主稿） | 改写渠道 | 写稿日 | 计划发布日 | 状态 | 稿件路径 | 归因 |
|---|---|---|---|---|---|---|
| 第一篇 | 知乎（问答体） | 11-04 | 11-15 | 待审 | `2026-11-04-改写一-知乎.md` | `utm_source=zhihu` |
| 第一篇 | X（单条 / thread） | 11-04 | 11-22 | 待审 | `2026-11-04-改写一-X.md` | `utm_source=x` |
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


class PreflightTestCase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="preflight-test-")
        business_dir = os.path.join(self.root, "knowledge", "business")
        channel_dir = os.path.join(business_dir, "wechat")
        os.makedirs(channel_dir)
        self.business_dir = business_dir
        self.content_dir = channel_dir
        self.write(os.path.join(business_dir, "品牌口径.md"), BRAND)
        self.write(os.path.join(business_dir, "选题日历.md"), CALENDAR)
        self.write(os.path.join(channel_dir, "2026-11-04-第一篇.md"), GOOD_DRAFT)
        self.write(os.path.join(channel_dir, "2026-11-04-改写一-X.md"), X_DRAFT)
        self.write(os.path.join(channel_dir, "2026-11-04-改写一-知乎.md"), ZHIHU_DRAFT)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, path, text):
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)

    def check_by_id(self, checks, check_id):
        for check in checks:
            if check.id == check_id:
                return check
        self.fail("没有找到检查项 {}".format(check_id))

    def run_checks(self, draft_name, channel=None):
        path = os.path.join(self.content_dir, draft_name)
        return pf.run_checks(self.root, path, channel)

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

    # ---------- 逐项检查 ----------

    def test_clean_draft_passes_all_hard_checks(self):
        checks = self.run_checks("2026-11-04-第一篇.md")
        failed = [c.id for c in checks if c.status == pf.STATUS_FAIL]
        self.assertEqual(failed, [], "干净稿件不该有失败项：{}".format(failed))

    def test_forbidden_word_fails(self):
        self.write(
            os.path.join(self.content_dir, "2026-11-04-第一篇.md"),
            GOOD_DRAFT + "\n我们把躺赚写进正文。\n",
        )
        checks = self.run_checks("2026-11-04-第一篇.md")
        check = self.check_by_id(checks, "forbidden-term")
        self.assertEqual(check.status, pf.STATUS_FAIL)
        self.assertTrue(any("躺赚" in d for d in check.detail))

    def test_term_table_misuse_fails(self):
        self.write(
            os.path.join(self.content_dir, "2026-11-04-第一篇.md"),
            GOOD_DRAFT + "\n我们是小微创业。\n",
        )
        checks = self.run_checks("2026-11-04-第一篇.md")
        check = self.check_by_id(checks, "term-misuse")
        self.assertEqual(check.status, pf.STATUS_FAIL)
        self.assertTrue(any("小微创业" in d for d in check.detail))

    def test_we_char_counts_as_forbidden(self):
        self.write(
            os.path.join(self.content_dir, "2026-11-04-第一篇.md"),
            GOOD_DRAFT + "\n我们想看看。\n",
        )
        checks = self.run_checks("2026-11-04-第一篇.md")
        self.assertEqual(self.check_by_id(checks, "forbidden-term").status, pf.STATUS_FAIL)

    def test_fenced_code_is_skipped(self):
        self.write(
            os.path.join(self.content_dir, "2026-11-04-第一篇.md"),
            GOOD_DRAFT + "\n```\n躺赚\n```\n",
        )
        checks = self.run_checks("2026-11-04-第一篇.md")
        self.assertEqual(self.check_by_id(checks, "forbidden-term").status, pf.STATUS_OK)

    def test_draft_not_in_calendar_fails(self):
        self.write(os.path.join(self.content_dir, "2026-11-04-没登记.md"), GOOD_DRAFT)
        checks = self.run_checks("2026-11-04-没登记.md")
        self.assertEqual(self.check_by_id(checks, "calendar-entry").status, pf.STATUS_FAIL)

    def test_channel_mismatch_fails(self):
        self.write(
            os.path.join(self.content_dir, "2026-11-04-第一篇.md"),
            GOOD_DRAFT.replace("公众号（主稿）", "知乎"),
        )
        checks = self.run_checks("2026-11-04-第一篇.md")
        check = self.check_by_id(checks, "channel-match")
        self.assertEqual(check.status, pf.STATUS_FAIL)
        self.assertTrue(any("知乎" in d for d in check.detail))

    def test_channel_match_ignores_parenthetical(self):
        checks = self.run_checks("2026-11-04-改写一-X.md")
        self.assertEqual(self.check_by_id(checks, "channel-match").status, pf.STATUS_OK)

    def test_missing_registered_file_fails(self):
        os.remove(os.path.join(self.content_dir, "2026-11-04-第一篇.md"))
        checks = self.run_checks("2026-11-04-第一篇.md")
        self.assertEqual(self.check_by_id(checks, "draft-exists").status, pf.STATUS_FAIL)

    def test_missing_draft_is_reported_not_crashed(self):
        checks = self.run_checks("2026-11-04-不存在.md")
        self.assertEqual(self.check_by_id(checks, "draft-exists").status, pf.STATUS_FAIL)

    def test_brand_proposal_marker_is_warning_only(self):
        checks = self.run_checks("2026-11-04-第一篇.md")
        check = self.check_by_id(checks, "brand-settled")
        self.assertEqual(check.status, pf.STATUS_WARN)

    # ---------- 退出码 ----------

    def test_exit_code_zero_on_clean_draft(self):
        code = pf.main([os.path.join(self.content_dir, "2026-11-04-第一篇.md"), "--root", self.root])
        self.assertEqual(code, 0)

    def test_exit_code_nonzero_on_failure(self):
        self.write(
            os.path.join(self.content_dir, "2026-11-04-第一篇.md"),
            GOOD_DRAFT + "\n躺赚。\n",
        )
        code = pf.main([os.path.join(self.content_dir, "2026-11-04-第一篇.md"), "--root", self.root])
        self.assertEqual(code, 1)

    def test_exit_code_two_on_missing_file(self):
        code = pf.main([os.path.join(self.content_dir, "不存在.md"), "--root", self.root])
        self.assertEqual(code, 2)

    # ---------- 不改源文件 ----------

    def test_word_count_ignores_code_blocks(self):
        self.assertEqual(pf.word_count("你好\n```\n代码\n```\n世界"), 4)

    def test_x_draft_word_count_checked_per_block(self):
        self.write(
            os.path.join(self.content_dir, "2026-11-04-改写一-X.md"),
            "# 第一篇（X 短帖改写）\n\n> **渠道**：X（改写稿）\n\n"
            "## 版本 A：单条帖（首发，≤200 字）\n\n" + "字" * 250 + "\n\n"
            "## 版本 B：thread（3 条，每条 ≤140 字）\n\n短。\n",
        )
        checks = self.run_checks("2026-11-04-改写一-X.md")
        check = self.check_by_id(checks, "word-count")
        self.assertEqual(check.status, pf.STATUS_WARN)
        self.assertTrue(any("250 字" in d for d in check.detail))

    def test_rewrite_channel_uses_rewrite_column(self):
        checks = self.run_checks("2026-11-04-改写一-知乎.md")
        check = self.check_by_id(checks, "channel-match")
        self.assertEqual(check.status, pf.STATUS_OK)
        self.assertTrue(any("知乎" in d for d in check.detail))

    def test_cta_missing_required_phrase_fails(self):
        self.write(
            os.path.join(self.content_dir, "2026-11-04-第一篇.md"),
            "# 第一篇\n\n> **渠道**：公众号（主稿）\n\n正文。\n\n看完记得点赞。\n",
        )
        checks = self.run_checks("2026-11-04-第一篇.md")
        check = self.check_by_id(checks, "cta-consistency")
        self.assertEqual(check.status, pf.STATUS_FAIL)
        self.assertTrue(any("关注公众号" in d for d in check.detail))

    def test_cta_forbidden_word_fails(self):
        self.write(
            os.path.join(self.content_dir, "2026-11-04-第一篇.md"),
            GOOD_DRAFT + "\n关注公众号，或者扫二维码。\n",
        )
        checks = self.run_checks("2026-11-04-第一篇.md")
        check = self.check_by_id(checks, "cta-consistency")
        self.assertEqual(check.status, pf.STATUS_FAIL)
        self.assertTrue(any("二维码" in d for d in check.detail))

    def test_cta_present_passes(self):
        self.write(
            os.path.join(self.content_dir, "2026-11-04-第一篇.md"),
            GOOD_DRAFT + "\n关注公众号，后续更新第一时间看到。\n",
        )
        checks = self.run_checks("2026-11-04-第一篇.md")
        self.assertEqual(self.check_by_id(checks, "cta-consistency").status, pf.STATUS_OK)

    def test_cta_check_warns_when_spec_column_missing(self):
        brand_path = os.path.join(self.business_dir, "品牌口径.md")
        with open(brand_path, encoding="utf-8") as handle:
            text = handle.read()
        text = text.replace(" | CTA 口径 |", " |").replace(
            " | 关注公众号；不得出现 链接、二维码、邮箱 |", " |"
        )
        self.write(brand_path, text)
        checks = self.run_checks("2026-11-04-第一篇.md")
        check = self.check_by_id(checks, "cta-consistency")
        self.assertEqual(check.status, pf.STATUS_WARN)
        self.assertTrue(any("CTA 口径列" in d for d in check.detail))

    def test_cta_uses_channel_specific_spec(self):
        checks = self.run_checks("2026-11-04-改写一-知乎.md")
        check = self.check_by_id(checks, "cta-consistency")
        self.assertIn(check.status, (pf.STATUS_OK, pf.STATUS_FAIL))

    def test_rewrite_channel_mismatch_fails(self):
        self.write(
            os.path.join(self.content_dir, "2026-11-04-改写一-知乎.md"),
            ZHIHU_DRAFT.replace("知乎（问答体）", "X（改写稿）"),
        )
        checks = self.run_checks("2026-11-04-改写一-知乎.md")
        self.assertEqual(self.check_by_id(checks, "channel-match").status, pf.STATUS_FAIL)

    def test_source_files_not_modified(self):
        brand_path = os.path.join(self.business_dir, "品牌口径.md")
        before = os.stat(brand_path).st_mtime_ns
        with open(brand_path, encoding="utf-8") as handle:
            content_before = handle.read()
        self.run_checks("2026-11-04-第一篇.md")
        with open(brand_path, encoding="utf-8") as handle:
            content_after = handle.read()
        self.assertEqual(content_before, content_after)
        self.assertEqual(before, os.stat(brand_path).st_mtime_ns)


class RealRepoRegressionTests(unittest.TestCase):
    """用仓库里真实的品牌口径与稿件跑整条 run_checks。

    回归用例：2026-11-04 12:34 版本里 ``forbidden_terms`` 被同名函数覆盖，
    ``run_checks`` 解包失败，所有稿件直接崩溃。只测抽取函数抓不到这类问题，
    必须从 run_checks 入口跑一遍。
    """

    def test_run_checks_on_real_brand_with_cta_column(self):
        brand = os.path.join(ROOT, "knowledge", "business", "品牌口径.md")
        draft = os.path.join(
            ROOT, "knowledge", "business", "wechat", "2026-11-04-四个AI角色的组织设计.md"
        )
        for path in (brand, draft):
            if not os.path.exists(path):
                self.skipTest("真实仓库文件不存在：{}".format(path))

        checks = pf.run_checks(ROOT, draft)
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


if __name__ == "__main__":
    unittest.main()
