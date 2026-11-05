#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""opc-workflow 的隔离实例集成测试。"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONTENT_ID_RE = re.compile(r"^content-\d{8}-\d{12}-[0-9a-f]{8}$")
PUBLICATION_ID_RE = re.compile(r"^publication-\d{8}-\d{12}-[0-9a-f]{8}$")


def parse_frontmatter(path):
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if len(lines) < 3 or lines[0] != "---":
        raise AssertionError("测试记录缺少 frontmatter 起始标记")
    try:
        end = lines.index("---", 1)
    except ValueError as error:
        raise AssertionError("测试记录缺少 frontmatter 结束标记") from error
    return json.loads("\n".join(lines[1:end])), text


def write_frontmatter(path, record):
    text = path.read_text(encoding="utf-8")
    marker = text.find("\n---\n", 4)
    if marker < 0:
        raise AssertionError("测试记录缺少 frontmatter 结束标记")
    body = text[marker + len("\n---\n") :]
    path.write_text(
        "---\n" + json.dumps(record, ensure_ascii=False, indent=2) + "\n---\n" + body,
        encoding="utf-8",
    )


class WorkflowTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="opc-workflow-test-")
        self.addCleanup(self.temp.cleanup)
        self.instance = Path(self.temp.name)
        (self.instance / ".opc").mkdir()
        (self.instance / "knowledge" / "business").mkdir(parents=True)
        (self.instance / ".opc" / "instance.json").write_text(
            json.dumps({"kind": "opc-instance", "version": 1}),
            encoding="utf-8",
        )
        (self.instance / "roles.json").write_text(
            json.dumps(
                {
                    "roles": [
                        {"name": "gm", "enabled": True},
                        {"name": "content", "enabled": True},
                        {"name": "growth", "enabled": True},
                        {"name": "dev", "enabled": True},
                        {"name": "disabled", "enabled": False},
                    ]
                }
            ),
            encoding="utf-8",
        )
        (self.instance / "channels.json").write_text(
            json.dumps(
                {
                    "channels": [
                        {"id": "wechat", "name": "公众号", "enabled": True},
                        {"id": "x", "name": "X", "enabled": False},
                    ]
                }
            ),
            encoding="utf-8",
        )
        # 工具住在实例里：根目录由脚本位置决定，与当前工作目录无关
        self.tools = self.instance / "tools"
        self.tools.mkdir()
        self.workflow = self.tools / "opc-workflow"
        shutil.copy(ROOT / "tools" / "opc-workflow", self.workflow)
        self.workflow.chmod(0o755)

    def run_workflow(self, *args, env=None, cwd=None):
        command = [sys.executable, str(self.workflow), *args]
        process_env = os.environ.copy()
        process_env.pop("OPC_ROLE", None)
        if env:
            process_env.update(env)
        return subprocess.run(
            command,
            text=True,
            capture_output=True,
            env=process_env,
            cwd=str(cwd) if cwd else None,
            check=False,
        )

    def content_cards(self):
        return sorted((self.instance / "knowledge" / "content").glob("*/内容卡.md"))

    def valid_record(self, content_id="content-20261105-120000000000-a1b2c3d4"):
        created_at = "2026-11-05T12:00:00.000000+00:00"
        return {
            "schema_version": 1,
            "record_type": "content",
            "content_id": content_id,
            "title": "手工编辑后的标题",
            "status": "proposed",
            "created_at": created_at,
            "actor": "content",
            "events": [
                {
                    "action": "create",
                    "at": created_at,
                    "actor": "content",
                    "to_status": "proposed",
                }
            ],
        }

    def write_card(self, directory_id, record=None, raw_frontmatter=None):
        package = self.instance / "knowledge" / "content" / directory_id
        package.mkdir(parents=True, exist_ok=True)
        if raw_frontmatter is None:
            raw_frontmatter = json.dumps(record, ensure_ascii=False, indent=2)
        card = package / "内容卡.md"
        card.write_text(
            "---\n{}\n---\n\n# 内容卡\n".format(raw_frontmatter),
            encoding="utf-8",
        )
        return card

    def create_content(self, title="审核链路", target_date=None):
        args = ["create-content", "--title", title]
        if target_date is not None:
            args.extend(["--target-date", target_date])
        result = self.run_workflow(*args)
        self.assertEqual(0, result.returncode, result.stderr)
        card = self.content_cards()[-1]
        record, _ = parse_frontmatter(card)
        return record["content_id"], card

    def main_draft(self, content_id):
        return self.instance / "knowledge" / "content" / content_id / "主稿.md"

    def publication_cards(self):
        return sorted(
            (self.instance / "knowledge" / "content").glob(
                "*/publications/*/发布卡.md"
            )
        )

    def publication_draft(self, publication_id):
        cards = [
            card for card in self.publication_cards() if card.parent.name == publication_id
        ]
        self.assertEqual(1, len(cards))
        return cards[0].parent / "渠道稿.md"

    def transition(self, content_id, *args, actor):
        return self.run_workflow(
            "transition",
            content_id,
            *args,
            "--actor",
            actor,
        )

    def advance_to_reviewing(self, content_id, text="# 主稿\n\n第一版正文。\n"):
        drafting = self.transition(content_id, "--to", "drafting", actor="content")
        self.assertEqual(0, drafting.returncode, drafting.stderr)
        draft = self.main_draft(content_id)
        draft.write_text(text, encoding="utf-8")
        reviewing = self.transition(content_id, "--to", "reviewing", actor="content")
        self.assertEqual(0, reviewing.returncode, reviewing.stderr)
        return draft

    def create_ready_content(self, title="可发布主稿"):
        content_id, card = self.create_content(title=title)
        self.advance_to_reviewing(content_id)
        approved = self.transition(
            content_id,
            "--decision",
            "approved",
            actor="gm",
        )
        self.assertEqual(0, approved.returncode, approved.stderr)
        return content_id, card

    def create_publication(self, content_id, channel="wechat"):
        result = self.run_workflow(
            "create-publication",
            content_id,
            "--channel",
            channel,
            "--actor",
            "gm",
        )
        self.assertEqual(0, result.returncode, result.stderr)
        card = self.publication_cards()[-1]
        record, _ = parse_frontmatter(card)
        return record["publication_id"], card

    def create_scheduled_publication(self):
        content_id, _content_card = self.create_ready_content()
        publication_id, publication_card = self.create_publication(content_id)
        self.publication_draft(publication_id).write_text(
            "# 渠道稿\n\n已完成适配。\n",
            encoding="utf-8",
        )
        reviewed = self.transition(
            publication_id,
            "--to",
            "reviewing",
            actor="content",
        )
        self.assertEqual(0, reviewed.returncode, reviewed.stderr)
        approved = self.transition(
            publication_id,
            "--decision",
            "approved",
            actor="gm",
        )
        self.assertEqual(0, approved.returncode, approved.stderr)
        scheduled = self.transition(
            publication_id,
            "--to",
            "scheduled",
            "--planned-at",
            "2026-11-20T09:00:00+08:00",
            "--timezone",
            "Asia/Shanghai",
            actor="gm",
        )
        self.assertEqual(0, scheduled.returncode, scheduled.stderr)
        return publication_id, publication_card

    def create_published_publication(self):
        publication_id, publication_card = self.create_scheduled_publication()
        published = self.publish(publication_id)
        self.assertEqual(0, published.returncode, published.stderr)
        return publication_id, publication_card

    def write_inbox(self, role, lines):
        inbox = self.instance / "knowledge" / "inbox"
        inbox.mkdir(parents=True, exist_ok=True)
        (inbox / f"{role}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def write_team(self, rows):
        team = self.instance / "knowledge" / "team.md"
        team.parent.mkdir(parents=True, exist_ok=True)
        body = [
            "# 团队名册",
            "",
            "| 角色 | 终端名 | 模板名 | CLI | 负责的子树 |",
            "|---|---|---|---|---|",
        ]
        body.extend(rows)
        team.write_text("\n".join(body) + "\n", encoding="utf-8")

    def dashboard_path(self):
        return self.instance / "knowledge" / "business" / "dashboard.json"

    def dashboard(self):
        return json.loads(self.dashboard_path().read_text(encoding="utf-8"))

    def publish(self, publication_id, *args, actor="gm"):
        return self.transition(
            publication_id,
            "--to",
            "published",
            "--actual-at",
            "2026-11-20T09:07:00+08:00",
            "--url",
            "https://example.com/posts/launch",
            *args,
            actor=actor,
        )

    def growth_dir(self):
        return self.instance / "knowledge" / "business" / "growth"

    def write_metric_catalog(self, metrics):
        self.growth_dir().mkdir(parents=True, exist_ok=True)
        record = {
            "schema_version": 1,
            "record_type": "metric_catalog",
            "metrics": metrics,
        }
        (self.growth_dir() / "指标.md").write_text(
            "---\n{}\n---\n\n# 指标目录\n".format(
                json.dumps(record, ensure_ascii=False, indent=2)
            ),
            encoding="utf-8",
        )

    def metric_catalog(self):
        self.write_metric_catalog(
            [
                {
                    "key": "views",
                    "label": "阅读量",
                    "unit": "count",
                    "aggregation": "sum",
                    "scope": "publication",
                    "channels": ["wechat"],
                },
                {
                    "key": "likes",
                    "label": "点赞数",
                    "unit": "count",
                    "aggregation": "sum",
                    "scope": "publication",
                    "channels": ["wechat"],
                },
                {
                    "key": "clicks",
                    "label": "点击量",
                    "unit": "count",
                    "aggregation": "sum",
                    "scope": "publication",
                    "channels": ["wechat"],
                },
                {
                    "key": "followers",
                    "label": "粉丝数",
                    "unit": "count",
                    "aggregation": "latest",
                    "scope": "channel",
                    "channels": ["wechat"],
                },
            ]
        )

    def publication_metrics_path(self, publication_id):
        cards = [
            card for card in self.publication_cards() if card.parent.name == publication_id
        ]
        self.assertEqual(1, len(cards))
        return cards[0].parent / "指标.md"

    def channel_snapshots_path(self):
        return self.growth_dir() / "渠道快照.md"

    def record_metrics(self, publication_id, window="48h", values=None, *args, actor="growth"):
        if values is None:
            values = {"views": 1234}
        return self.run_workflow(
            "record-metrics",
            publication_id,
            "--window",
            window,
            "--observed-at",
            "2026-11-21T09:00:00+08:00",
            "--source",
            "平台后台",
            "--values",
            json.dumps(values, ensure_ascii=False),
            *args,
            "--actor",
            actor,
        )

    def record_channel_snapshot(self, values=None, *args, actor="growth"):
        if values is None:
            values = {"followers": 5000}
        return self.run_workflow(
            "record-channel-snapshot",
            "--channel",
            "wechat",
            "--observed-at",
            "2026-11-21T09:00:00+08:00",
            "--source",
            "平台后台",
            "--values",
            json.dumps(values, ensure_ascii=False),
            *args,
            "--actor",
            actor,
        )

    # ---------- create-content ----------

    def test_create_content_writes_minimal_proposed_card_at_fixed_path(self):
        result = self.run_workflow("create-content", "--title", "第一条选题")

        self.assertEqual(0, result.returncode, result.stderr)
        cards = self.content_cards()
        self.assertEqual(1, len(cards))
        record, text = parse_frontmatter(cards[0])
        content_id = record["content_id"]
        self.assertRegex(content_id, CONTENT_ID_RE)
        self.assertEqual(content_id, cards[0].parent.name)
        self.assertEqual(1, record["schema_version"])
        self.assertEqual("content", record["record_type"])
        self.assertEqual("第一条选题", record["title"])
        self.assertEqual("proposed", record["status"])
        self.assertEqual("content", record["actor"])
        self.assertRegex(record["created_at"], r"\+00:00$")
        self.assertEqual(
            [
                {
                    "action": "create",
                    "at": record["created_at"],
                    "actor": "content",
                    "to_status": "proposed",
                }
            ],
            record["events"],
        )
        self.assertNotIn("source", record)
        self.assertNotIn("summary", record)
        self.assertIn("# 内容卡", text)
        self.assertIn(content_id, result.stdout)
        self.assertIn("knowledge/content/", result.stdout)

    def test_create_content_accepts_optional_metadata_and_actor(self):
        result = self.run_workflow(
            "create-content",
            "--title",
            "带来源的选题",
            "--source",
            "行业访谈",
            "--summary",
            "关注一个具体问题。",
            "--actor",
            "gm",
        )

        self.assertEqual(0, result.returncode, result.stderr)
        record, _ = parse_frontmatter(self.content_cards()[0])
        self.assertEqual("行业访谈", record["source"])
        self.assertEqual("关注一个具体问题。", record["summary"])
        self.assertEqual("gm", record["actor"])
        self.assertEqual("gm", record["events"][0]["actor"])

    def test_create_content_rejects_invalid_target_date(self):
        for value in ("2026-02-30", "20261120"):
            with self.subTest(value=value):
                result = self.run_workflow(
                    "create-content",
                    "--title",
                    "错误日期",
                    "--target-date",
                    value,
                )

                self.assertEqual(1, result.returncode)
                self.assertIn("YYYY-MM-DD", result.stderr)
                self.assertEqual([], self.content_cards())

    def test_create_content_uses_opc_role_when_actor_is_omitted(self):
        result = self.run_workflow(
            "create-content",
            "--title",
            "采集角色提议",
            env={"OPC_ROLE": "gm"},
        )

        self.assertEqual(0, result.returncode, result.stderr)
        record, _ = parse_frontmatter(self.content_cards()[0])
        self.assertEqual("gm", record["actor"])

    def test_two_fast_creations_never_reuse_an_id(self):
        first = self.run_workflow("create-content", "--title", "第一条")
        second = self.run_workflow("create-content", "--title", "第二条")

        self.assertEqual(0, first.returncode, first.stderr)
        self.assertEqual(0, second.returncode, second.stderr)
        cards = self.content_cards()
        self.assertEqual(2, len(cards))
        self.assertNotEqual(cards[0].parent.name, cards[1].parent.name)
        titles = {parse_frontmatter(card)[0]["title"] for card in cards}
        self.assertEqual({"第一条", "第二条"}, titles)

    def test_create_content_rejects_unknown_actor_without_writing(self):
        result = self.run_workflow(
            "create-content",
            "--title",
            "错误 actor",
            "--actor",
            "researcher",
        )

        self.assertEqual(1, result.returncode)
        self.assertIn("非法 actor", result.stderr)
        self.assertFalse((self.instance / "knowledge" / "content").exists())

    def test_create_content_writes_into_its_own_instance_not_the_working_directory(self):
        elsewhere = Path(self.temp.name + "-elsewhere")
        elsewhere.mkdir()
        self.addCleanup(shutil.rmtree, elsewhere, True)

        result = self.run_workflow(
            "create-content",
            "--title",
            "不从工作目录写",
            cwd=elsewhere,
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(1, len(self.content_cards()))
        self.assertEqual([], list(elsewhere.iterdir()))

    def test_create_content_rejects_a_root_that_is_not_an_opc_instance(self):
        outside = Path(self.temp.name + "-outside-instance")
        outside.mkdir()
        self.addCleanup(shutil.rmtree, outside, True)
        (outside / "tools").mkdir()
        tool = outside / "tools" / "opc-workflow"
        shutil.copy(ROOT / "tools" / "opc-workflow", tool)

        result = subprocess.run(
            [sys.executable, str(tool), "create-content", "--title", "越界"],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(1, result.returncode)
        self.assertIn("不是 OPC 实例", result.stderr)
        self.assertEqual(
            [outside / "tools"],
            sorted(outside.iterdir()),
            "拒绝执行时不得在实例外创建任何文件",
        )

    def test_create_content_reports_the_actor_it_attributed(self):
        # 归属是审计字段：调用方必须一眼看见它被记成了谁，误用才能当场发现
        result = self.run_workflow(
            "create-content",
            "--title",
            "归属可见",
            "--actor",
            "gm",
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("actor=gm", result.stdout)

    def test_create_content_refuses_to_impersonate_another_role(self):
        result = self.run_workflow(
            "create-content",
            "--title",
            "冒充 gm",
            "--actor",
            "gm",
            env={"OPC_ROLE": "content"},
        )

        self.assertEqual(1, result.returncode)
        self.assertIn("不一致", result.stderr)
        self.assertEqual([], self.content_cards())

    def test_create_content_refuses_a_disabled_role(self):
        result = self.run_workflow(
            "create-content",
            "--title",
            "停用角色",
            "--actor",
            "disabled",
        )

        self.assertEqual(1, result.returncode)
        self.assertIn("停用", result.stderr)
        self.assertEqual([], self.content_cards())

    # ---------- create-publication ----------

    def test_gm_creates_publication_for_ready_content_at_fixed_path(self):
        content_id, _content_card = self.create_ready_content()

        result = self.run_workflow(
            "create-publication",
            content_id,
            "--channel",
            "wechat",
            "--actor",
            "gm",
        )

        self.assertEqual(0, result.returncode, result.stderr)
        cards = self.publication_cards()
        self.assertEqual(1, len(cards))
        record, text = parse_frontmatter(cards[0])
        publication_id = record["publication_id"]
        self.assertRegex(publication_id, PUBLICATION_ID_RE)
        self.assertEqual(publication_id, cards[0].parent.name)
        self.assertEqual(
            self.instance
            / "knowledge"
            / "content"
            / content_id
            / "publications"
            / publication_id,
            cards[0].parent,
        )
        self.assertEqual("publication", record["record_type"])
        self.assertEqual(content_id, record["content_id"])
        self.assertEqual("wechat", record["channel"])
        self.assertEqual("adapting", record["status"])
        self.assertEqual("gm", record["actor"])
        self.assertEqual("渠道稿.md", record["channel_draft"])
        self.assertRegex(record["created_at"], r"\+00:00$")
        self.assertEqual(
            {
                "action": "create",
                "at": record["created_at"],
                "actor": "gm",
                "to_status": "adapting",
            },
            record["events"][0],
        )
        self.assertTrue((cards[0].parent / "渠道稿.md").is_file())
        self.assertIn("# 发布卡", text)
        self.assertIn(publication_id, result.stdout)
        self.assertIn("actor=gm", result.stdout)

    def test_create_publication_requires_ready_content_enabled_channel_and_gm(self):
        content_id, _card = self.create_content()
        cases = (
            (["--channel", "wechat", "--actor", "gm"], "ready"),
            (["--channel", "missing", "--actor", "gm"], "未知 channel"),
            (["--channel", "x", "--actor", "gm"], "停用"),
            (["--channel", "wechat", "--actor", "content"], "gm"),
        )
        for arguments, message in cases:
            with self.subTest(arguments=arguments):
                result = self.run_workflow(
                    "create-publication",
                    content_id,
                    *arguments,
                )
                self.assertEqual(1, result.returncode)
                self.assertIn(message, result.stderr)
                self.assertEqual([], self.publication_cards())

    def test_two_fast_publications_never_reuse_an_id(self):
        content_id, _card = self.create_ready_content()

        first_id, _first_card = self.create_publication(content_id)
        second_id, _second_card = self.create_publication(content_id)

        self.assertNotEqual(first_id, second_id)
        self.assertEqual(2, len(self.publication_cards()))

    def test_validate_rejects_broken_publication_reference_and_unknown_channel(self):
        content_id, _content_card = self.create_ready_content()
        _publication_id, publication_card = self.create_publication(content_id)
        record, text = parse_frontmatter(publication_card)
        record["content_id"] = "content-20261105-120000000000-deadbeef"
        record["channel"] = "missing"
        body = text.split("---", 2)[2]
        publication_card.write_text(
            "---\n{}\n---{}".format(
                json.dumps(record, ensure_ascii=False, indent=2),
                body,
            ),
            encoding="utf-8",
        )

        result = self.run_workflow("validate")

        self.assertEqual(1, result.returncode)
        self.assertIn("断裂 content_id", result.stderr)
        self.assertIn("未知 channel", result.stderr)
        self.assertIn("发布卡.md", result.stderr)

    def test_validate_rejects_publication_when_parent_content_card_is_missing(self):
        content_id, content_card = self.create_ready_content()
        self.create_publication(content_id)
        content_card.unlink()

        result = self.run_workflow("validate")

        self.assertEqual(1, result.returncode)
        self.assertIn("publication 引用缺失内容卡", result.stderr)

    def test_create_publication_rejects_invalid_configured_channel_key(self):
        content_id, _content_card = self.create_ready_content()
        (self.instance / "channels.json").write_text(
            json.dumps(
                {
                    "channels": [
                        {"id": "../escape", "name": "错误频道", "enabled": True}
                    ]
                }
            ),
            encoding="utf-8",
        )

        result = self.run_workflow(
            "create-publication",
            content_id,
            "--channel",
            "../escape",
            "--actor",
            "gm",
        )

        self.assertEqual(1, result.returncode)
        self.assertIn("channel id", result.stderr)
        self.assertEqual([], self.publication_cards())

    def test_validate_rejects_duplicate_publication_ids(self):
        first_content_id, _card = self.create_ready_content(title="第一篇")
        publication_id, first_publication = self.create_publication(first_content_id)
        second_content_id, _card = self.create_ready_content(title="第二篇")
        second_package = (
            self.instance
            / "knowledge"
            / "content"
            / second_content_id
            / "publications"
            / publication_id
        )
        second_package.mkdir(parents=True)
        record, text = parse_frontmatter(first_publication)
        record["content_id"] = second_content_id
        body = text.split("---", 2)[2]
        (second_package / "发布卡.md").write_text(
            "---\n{}\n---{}".format(
                json.dumps(record, ensure_ascii=False, indent=2),
                body,
            ),
            encoding="utf-8",
        )
        (second_package / "渠道稿.md").write_text("# 第二篇\n", encoding="utf-8")

        result = self.run_workflow("validate")

        self.assertEqual(1, result.returncode)
        self.assertIn("重复 publication_id", result.stderr)
        self.assertIn(first_content_id, result.stderr)
        self.assertIn(second_content_id, result.stderr)

    # ---------- publication transition / approval ----------

    def test_publication_review_and_schedule_flow_binds_channel_draft_hash(self):
        content_id, _content_card = self.create_ready_content()
        publication_id, publication_card = self.create_publication(content_id)
        draft = self.publication_draft(publication_id)
        body = "# 渠道稿\n\n渠道适配正文。\n"
        draft.write_text(body, encoding="utf-8")

        reviewing = self.transition(
            publication_id,
            "--to",
            "reviewing",
            actor="content",
        )
        self.assertEqual(0, reviewing.returncode, reviewing.stderr)
        record, _ = parse_frontmatter(publication_card)
        expected_hash = "sha256:" + hashlib.sha256(body.encode()).hexdigest()
        self.assertEqual("reviewing", record["status"])
        self.assertEqual(
            {
                "status": "pending",
                "requested_at": record["approval"]["requested_at"],
                "requested_by": "content",
                "artifact": "渠道稿.md",
                "artifact_hash": expected_hash,
            },
            record["approval"],
        )

        approved = self.transition(
            publication_id,
            "--decision",
            "approved",
            actor="gm",
        )
        self.assertEqual(0, approved.returncode, approved.stderr)
        record, _ = parse_frontmatter(publication_card)
        self.assertEqual("reviewing", record["status"])
        self.assertEqual("approved", record["approval"]["status"])

        scheduled = self.transition(
            publication_id,
            "--to",
            "scheduled",
            "--planned-at",
            "2026-11-20T09:00:00+08:00",
            "--timezone",
            "Asia/Shanghai",
            actor="gm",
        )
        self.assertEqual(0, scheduled.returncode, scheduled.stderr)
        record, _ = parse_frontmatter(publication_card)
        self.assertEqual("scheduled", record["status"])
        self.assertEqual("2026-11-20T09:00:00+08:00", record["schedule"]["planned_at"])
        self.assertEqual("Asia/Shanghai", record["schedule"]["timezone"])
        self.assertNotIn("published_at", record)
        self.assertEqual("schedule", record["events"][-1]["action"])
        self.assertEqual(0, self.run_workflow("validate").returncode)

    def test_publication_cannot_schedule_without_valid_approved_draft(self):
        content_id, _content_card = self.create_ready_content()
        publication_id, _publication_card = self.create_publication(content_id)

        result = self.transition(
            publication_id,
            "--to",
            "scheduled",
            "--planned-at",
            "2026-11-20T09:00:00+08:00",
            "--timezone",
            "Asia/Shanghai",
            actor="gm",
        )

        self.assertEqual(1, result.returncode)
        self.assertIn("approved", result.stderr)

    def test_publication_edit_after_approval_is_stale_and_can_be_reapproved(self):
        content_id, _content_card = self.create_ready_content()
        publication_id, publication_card = self.create_publication(content_id)
        draft = self.publication_draft(publication_id)
        draft.write_text("# 渠道稿\n\n第一版。\n", encoding="utf-8")
        self.assertEqual(
            0,
            self.transition(
                publication_id,
                "--to",
                "reviewing",
                actor="content",
            ).returncode,
        )
        self.assertEqual(
            0,
            self.transition(
                publication_id,
                "--decision",
                "approved",
                actor="gm",
            ).returncode,
        )
        before, _ = parse_frontmatter(publication_card)
        first_hash = before["approval"]["artifact_hash"]

        draft.write_text("# 渠道稿\n\n审批后修改。\n", encoding="utf-8")

        stale = self.run_workflow("validate")
        self.assertEqual(1, stale.returncode)
        self.assertIn("stale approval", stale.stderr)
        blocked = self.transition(
            publication_id,
            "--to",
            "scheduled",
            "--planned-at",
            "2026-11-20T09:00:00+08:00",
            "--timezone",
            "Asia/Shanghai",
            actor="gm",
        )
        self.assertEqual(1, blocked.returncode)
        self.assertIn("stale approval", blocked.stderr)

        resubmitted = self.transition(
            publication_id,
            "--to",
            "reviewing",
            actor="content",
        )
        self.assertEqual(0, resubmitted.returncode, resubmitted.stderr)
        reapproved = self.transition(
            publication_id,
            "--decision",
            "approved",
            actor="gm",
        )
        self.assertEqual(0, reapproved.returncode, reapproved.stderr)
        final, _ = parse_frontmatter(publication_card)
        self.assertNotEqual(first_hash, final["approval"]["artifact_hash"])
        decisions = [
            event
            for event in final["events"]
            if event["action"] == "approval_decision"
        ]
        self.assertEqual(2, len(decisions))
        self.assertEqual(first_hash, decisions[0]["artifact_hash"])

    def test_gm_reschedules_with_reason_and_preserves_previous_plan(self):
        publication_id, publication_card = self.create_scheduled_publication()

        result = self.transition(
            publication_id,
            "--to",
            "scheduled",
            "--planned-at",
            "2026-11-22T10:30:00+08:00",
            "--timezone",
            "Asia/Shanghai",
            "--note",
            "配合活动窗口。",
            actor="gm",
        )

        self.assertEqual(0, result.returncode, result.stderr)
        record, _ = parse_frontmatter(publication_card)
        self.assertEqual("scheduled", record["status"])
        self.assertEqual("2026-11-22T10:30:00+08:00", record["schedule"]["planned_at"])
        event = record["events"][-1]
        self.assertEqual("reschedule", event["action"])
        self.assertEqual("2026-11-20T09:00:00+08:00", event["previous_planned_at"])
        self.assertEqual("Asia/Shanghai", event["previous_timezone"])
        self.assertEqual("配合活动窗口。", event["note"])
        self.assertEqual(0, self.run_workflow("validate").returncode)

    def test_gm_confirms_scheduled_publication_with_actual_facts(self):
        publication_id, publication_card = self.create_scheduled_publication()

        result = self.publish(
            publication_id,
            "--external-id",
            "platform-post-42",
        )

        self.assertEqual(0, result.returncode, result.stderr)
        record, _ = parse_frontmatter(publication_card)
        self.assertEqual("published", record["status"])
        self.assertEqual(
            {
                "published_at": "2026-11-20T09:07:00+08:00",
                "url": "https://example.com/posts/launch",
                "external_id": "platform-post-42",
                "recorded_at": record["publication"]["recorded_at"],
                "recorded_by": "gm",
            },
            record["publication"],
        )
        self.assertEqual("2026-11-20T09:00:00+08:00", record["schedule"]["planned_at"])
        event = record["events"][-1]
        self.assertEqual("publish", event["action"])
        self.assertEqual("scheduled", event["from_status"])
        self.assertEqual("published", event["to_status"])
        self.assertEqual("2026-11-20T09:07:00+08:00", event["published_at"])
        self.assertEqual("https://example.com/posts/launch", event["url"])
        self.assertEqual("platform-post-42", event["external_id"])
        self.assertEqual(0, self.run_workflow("validate").returncode)

    def test_publish_without_external_id_keeps_it_absent(self):
        publication_id, publication_card = self.create_scheduled_publication()

        result = self.publish(publication_id)

        self.assertEqual(0, result.returncode, result.stderr)
        record, _ = parse_frontmatter(publication_card)
        self.assertNotIn("external_id", record["publication"])
        self.assertNotIn("external_id", record["events"][-1])
        self.assertEqual(0, self.run_workflow("validate").returncode)

    def test_publish_requires_scheduled_state_and_gm(self):
        content_id, _content_card = self.create_ready_content()
        publication_id, publication_card = self.create_publication(content_id)
        before = publication_card.read_bytes()
        arguments = (
            "--to",
            "published",
            "--actual-at",
            "2026-11-20T09:07:00+08:00",
            "--url",
            "https://example.com/post",
        )

        not_scheduled = self.transition(publication_id, *arguments, actor="gm")
        self.assertEqual(1, not_scheduled.returncode)
        self.assertIn("scheduled", not_scheduled.stderr)
        self.assertEqual(before, publication_card.read_bytes())

    def test_publish_requires_actual_time_and_http_url(self):
        publication_id, publication_card = self.create_scheduled_publication()
        before = publication_card.read_bytes()

        for arguments, message in (
            (
                (
                    "--to",
                    "published",
                    "--actual-at",
                    "2026-11-20T09:07:00",
                    "--url",
                    "https://example.com/post",
                ),
                "offset-aware",
            ),
            (
                (
                    "--to",
                    "published",
                    "--actual-at",
                    "2026-11-20T09:07:00+08:00",
                    "--url",
                    "javascript:alert(1)",
                ),
                "URL",
            ),
        ):
            with self.subTest(message=message):
                result = self.transition(publication_id, *arguments, actor="gm")
                self.assertEqual(1, result.returncode)
                self.assertIn(message, result.stderr)
                self.assertEqual(before, publication_card.read_bytes())

    def test_publish_rejects_non_gm_actor(self):
        publication_id, publication_card = self.create_scheduled_publication()
        before = publication_card.read_bytes()

        result = self.publish(publication_id, actor="content")

        self.assertEqual(1, result.returncode)
        self.assertIn("gm", result.stderr)
        self.assertEqual(before, publication_card.read_bytes())

    def test_published_publication_cannot_return_to_prepublication_state(self):
        publication_id, publication_card = self.create_scheduled_publication()
        published = self.publish(publication_id)
        self.assertEqual(0, published.returncode, published.stderr)
        before = publication_card.read_bytes()

        for arguments in (
            (
                "--to",
                "scheduled",
                "--planned-at",
                "2026-11-22T10:30:00+08:00",
                "--timezone",
                "Asia/Shanghai",
                "--note",
                "再次排期",
            ),
            ("--to", "cancelled", "--note", "撤回"),
            (
                "--to",
                "published",
                "--actual-at",
                "2026-11-20T09:08:00+08:00",
                "--url",
                "https://example.com/posts/retry",
            ),
        ):
            with self.subTest(arguments=arguments):
                result = self.transition(publication_id, *arguments, actor="gm")
                self.assertEqual(1, result.returncode)
                self.assertEqual(before, publication_card.read_bytes())

    # ---------- growth metrics ----------

    def test_growth_records_immutable_publication_metric_windows(self):
        publication_id, publication_card = self.create_scheduled_publication()
        published = self.publish(publication_id)
        self.assertEqual(0, published.returncode, published.stderr)
        self.metric_catalog()
        publication_before, _ = parse_frontmatter(publication_card)

        first = self.record_metrics(
            publication_id,
            "48h",
            {"views": 1234, "likes": 0},
        )

        self.assertEqual(0, first.returncode, first.stderr)
        metrics = self.publication_metrics_path(publication_id)
        record, _ = parse_frontmatter(metrics)
        self.assertEqual("publication_metrics", record["record_type"])
        self.assertEqual(publication_id, record["publication_id"])
        self.assertEqual(
            [
                {
                    "window": "48h",
                    "observed_at": "2026-11-21T09:00:00+08:00",
                    "source": "平台后台",
                    "recorded_at": record["snapshots"][0]["recorded_at"],
                    "recorded_by": "growth",
                    "values": {"views": 1234, "likes": 0},
                }
            ],
            record["snapshots"],
        )

        second = self.record_metrics(publication_id, "7d", {"views": 2000})
        self.assertEqual(0, second.returncode, second.stderr)
        record["snapshots"].append(
            {
                "window": "7d",
                "observed_at": "2026-11-27T09:00:00+08:00",
                "source": "平台后台",
                "recorded_at": record["snapshots"][0]["recorded_at"],
                "recorded_by": "growth",
                "values": {"views": 2000},
            }
        )
        after, _ = parse_frontmatter(metrics)
        self.assertEqual(2, len(after["snapshots"]))
        self.assertEqual("48h", after["snapshots"][0]["window"])
        self.assertEqual("7d", after["snapshots"][1]["window"])

        before_duplicate = metrics.read_bytes()
        duplicate = self.record_metrics(publication_id, "48h", {"views": 9999})
        self.assertEqual(1, duplicate.returncode)
        self.assertIn("重复窗口", duplicate.stderr)
        self.assertEqual(before_duplicate, metrics.read_bytes())

        publication_after, _ = parse_frontmatter(publication_card)
        self.assertEqual(
            publication_before["schedule"],
            publication_after["schedule"],
        )
        self.assertEqual(
            publication_before["publication"],
            publication_after["publication"],
        )
        self.assertEqual(0, self.run_workflow("validate").returncode)

    def test_publication_metric_diagnostics_cover_unknown_key_scope_unit_and_source(self):
        publication_id, _publication_card = self.create_scheduled_publication()
        self.assertEqual(0, self.publish(publication_id).returncode)
        self.metric_catalog()

        cases = (
            (
                self.record_metrics(publication_id, "1d", {"unknown": 1}),
                "未注册",
            ),
            (
                self.record_metrics(publication_id, "1d", {"followers": 100}),
                "scope",
            ),
            (
                self.record_metrics(publication_id, "1d", {"views": 1}, "--source", ""),
                "source",
            ),
            (
                self.record_metrics(publication_id, "1d", {"views": "一千"}),
                "数值",
            ),
            (
                self.record_metrics(
                    publication_id,
                    "1d",
                    {"views": {"available": False, "reason": "平台不提供", "unit": "percent"}},
                ),
                "unit",
            ),
        )
        for result, message in cases:
            with self.subTest(message=message):
                self.assertEqual(1, result.returncode)
                self.assertIn(message, result.stderr)
        self.assertFalse(self.publication_metrics_path(publication_id).exists())

        self.write_metric_catalog(
            [
                {
                    "key": "views",
                    "label": "阅读量",
                    "unit": "count",
                    "aggregation": "sum",
                    "scope": "publication",
                    "channels": ["x"],
                }
            ]
        )
        unsupported = self.record_metrics(publication_id, "1d", {"views": 1})
        self.assertEqual(1, unsupported.returncode)
        self.assertIn("channel", unsupported.stderr)

    def test_channel_snapshot_stays_out_of_publication_metrics(self):
        publication_id, _publication_card = self.create_scheduled_publication()
        self.assertEqual(0, self.publish(publication_id).returncode)
        self.metric_catalog()
        self.assertEqual(
            0,
            self.record_metrics(publication_id, "48h", {"views": 1234}).returncode,
        )

        result = self.record_channel_snapshot({"followers": 5000})

        self.assertEqual(0, result.returncode, result.stderr)
        record, _ = parse_frontmatter(self.channel_snapshots_path())
        self.assertEqual("channel_snapshots", record["record_type"])
        self.assertEqual(
            [
                {
                    "channel": "wechat",
                    "observed_at": "2026-11-21T09:00:00+08:00",
                    "source": "平台后台",
                    "recorded_at": record["observations"][0]["recorded_at"],
                    "recorded_by": "growth",
                    "values": {"followers": 5000},
                }
            ],
            record["observations"],
        )
        metrics_text = self.publication_metrics_path(publication_id).read_text(
            encoding="utf-8"
        )
        self.assertNotIn("followers", metrics_text)
        self.assertNotIn(publication_id, self.channel_snapshots_path().read_text(encoding="utf-8"))

        wrong_scope = self.record_channel_snapshot({"views": 10})
        self.assertEqual(1, wrong_scope.returncode)
        self.assertIn("scope", wrong_scope.stderr)

        duplicate = self.record_channel_snapshot({"followers": 5001})
        self.assertEqual(1, duplicate.returncode)
        self.assertIn("重复观测", duplicate.stderr)

        equivalent_instant = self.record_channel_snapshot(
            {"followers": 5001},
            "--observed-at",
            "2026-11-21T01:00:00+00:00",
        )
        self.assertEqual(1, equivalent_instant.returncode)
        self.assertIn("重复观测", equivalent_instant.stderr)

        bad_actor = self.record_channel_snapshot({"followers": 5002}, actor="content")
        self.assertEqual(1, bad_actor.returncode)
        self.assertIn("growth", bad_actor.stderr)
        self.assertEqual(0, self.run_workflow("validate").returncode)

    def test_build_publication_summary_distinguishes_missing_unavailable_and_zero(self):
        publication_id, _publication_card = self.create_scheduled_publication()
        self.assertEqual(0, self.publish(publication_id).returncode)
        self.metric_catalog()
        recorded = self.record_metrics(
            publication_id,
            "48h",
            {
                "views": 0,
                "clicks": {"available": False, "reason": "平台不提供"},
            },
        )
        self.assertEqual(0, recorded.returncode, recorded.stderr)
        self.assertEqual(0, self.record_channel_snapshot({"followers": 5000}).returncode)

        result = self.run_workflow("build")

        self.assertEqual(0, result.returncode, result.stderr)
        view = (
            self.instance
            / "knowledge"
            / "business"
            / "wechat"
            / "发布记录.md"
        ).read_text(encoding="utf-8")
        self.assertIn("2026-11-20T09:07:00+08:00", view)
        self.assertIn("https://example.com/posts/launch", view)
        publication_record, _ = parse_frontmatter(
            next(
                card
                for card in self.publication_cards()
                if card.parent.name == publication_id
            )
        )
        content_id = publication_record["content_id"]
        self.assertIn(
            f"../../content/{content_id}/publications/{publication_id}/指标.md",
            view,
        )
        self.assertIn("0", view)
        self.assertIn("不可得", view)
        self.assertIn("缺失", view)
        self.assertIn("## 渠道账号观测", view)
        self.assertIn("5000", view)
        publication_rows = [
            line for line in view.splitlines() if publication_id in line
        ]
        self.assertEqual(1, len(publication_rows))
        self.assertNotIn("5000", publication_rows[0])

    def test_validate_rejects_directly_edited_publication_facts(self):
        publication_id, publication_card = self.create_scheduled_publication()
        self.assertEqual(0, self.publish(publication_id).returncode)

        record, text = parse_frontmatter(publication_card)
        record["publication"]["url"] = "https://example.com/other"
        publication_card.write_text(
            "---\n{}\n---{}".format(
                json.dumps(record, ensure_ascii=False, indent=2),
                text.split("---", 2)[2],
            ),
            encoding="utf-8",
        )
        mismatched = self.run_workflow("validate")
        self.assertEqual(1, mismatched.returncode)
        self.assertIn("publish event 不一致", mismatched.stderr)

        record["publication"]["url"] = "https://example.com/posts/launch"
        record["status"] = "scheduled"
        publication_card.write_text(
            "---\n{}\n---{}".format(
                json.dumps(record, ensure_ascii=False, indent=2),
                text.split("---", 2)[2],
            ),
            encoding="utf-8",
        )
        wrong_status = self.run_workflow("validate")
        self.assertEqual(1, wrong_status.returncode)
        self.assertIn("只有 published", wrong_status.stderr)

        record["status"] = "published"
        del record["publication"]
        publication_card.write_text(
            "---\n{}\n---{}".format(
                json.dumps(record, ensure_ascii=False, indent=2),
                text.split("---", 2)[2],
            ),
            encoding="utf-8",
        )
        missing_fact = self.run_workflow("validate")
        self.assertEqual(1, missing_fact.returncode)
        self.assertIn("publication 发布事实", missing_fact.stderr)

    def test_validate_rejects_inconsistent_metric_catalog_and_windows(self):
        publication_id, _publication_card = self.create_scheduled_publication()
        self.assertEqual(0, self.publish(publication_id).returncode)
        self.metric_catalog()
        self.assertEqual(
            0,
            self.record_metrics(publication_id, "48h", {"views": 1}).returncode,
        )
        metrics = self.publication_metrics_path(publication_id)
        record, text = parse_frontmatter(metrics)
        record["snapshots"].append(dict(record["snapshots"][0]))
        metrics.write_text(
            "---\n{}\n---{}".format(
                json.dumps(record, ensure_ascii=False, indent=2),
                text.split("---", 2)[2],
            ),
            encoding="utf-8",
        )

        duplicate = self.run_workflow("validate")
        self.assertEqual(1, duplicate.returncode)
        self.assertIn("重复窗口", duplicate.stderr)

        self.write_metric_catalog(
            [
                {
                    "key": "views",
                    "label": "阅读量",
                    "unit": "count",
                    "aggregation": "sum",
                    "scope": "publication",
                    "channels": ["wechat"],
                },
                {
                    "key": "views",
                    "label": "阅读率",
                    "unit": "percent",
                    "aggregation": "sum",
                    "scope": "publication",
                    "channels": ["wechat"],
                },
            ]
        )
        catalog_error = self.run_workflow("validate")
        self.assertEqual(1, catalog_error.returncode)
        self.assertIn("unit", catalog_error.stderr)

    def test_growth_metrics_require_published_publication(self):
        content_id, _content_card = self.create_ready_content()
        publication_id, _publication_card = self.create_publication(content_id)
        self.metric_catalog()

        result = self.record_metrics(publication_id, "48h", {"views": 1})

        self.assertEqual(1, result.returncode)
        self.assertIn("published", result.stderr)
        self.assertFalse(self.publication_metrics_path(publication_id).exists())

    def test_published_publication_allows_a_new_publication_for_retry(self):
        first_id, _first_card = self.create_scheduled_publication()
        first_record, _ = parse_frontmatter(
            next(
                card
                for card in self.publication_cards()
                if card.parent.name == first_id
            )
        )
        content_id = first_record["content_id"]
        self.assertEqual(0, self.publish(first_id).returncode)

        second_id, _second_card = self.create_publication(content_id)

        self.assertNotEqual(first_id, second_id)
        self.assertEqual(2, len(self.publication_cards()))
        first_record, _ = parse_frontmatter(
            next(
                card
                for card in self.publication_cards()
                if card.parent.name == first_id
            )
        )
        second_record, _ = parse_frontmatter(
            next(
                card
                for card in self.publication_cards()
                if card.parent.name == second_id
            )
        )
        self.assertEqual("published", first_record["status"])
        self.assertEqual("adapting", second_record["status"])

    def test_channel_snapshots_stay_in_their_channel_view(self):
        self.metric_catalog()
        self.assertEqual(0, self.record_channel_snapshot({"followers": 5000}).returncode)
        (self.instance / "channels.json").write_text(
            json.dumps(
                {
                    "channels": [
                        {"id": "wechat", "name": "公众号", "enabled": True},
                        {"id": "x", "name": "X", "enabled": True},
                    ]
                }
            ),
            encoding="utf-8",
        )

        result = self.run_workflow("build")

        self.assertEqual(0, result.returncode, result.stderr)
        wechat_view = (
            self.instance / "knowledge" / "business" / "wechat" / "发布记录.md"
        ).read_text(encoding="utf-8")
        x_view = (
            self.instance / "knowledge" / "business" / "x" / "发布记录.md"
        ).read_text(encoding="utf-8")
        self.assertIn("5000", wechat_view)
        self.assertNotIn("5000", x_view)
        self.assertIn("当前没有该渠道的账号级观测。", x_view)

    def test_validate_rejects_symlinked_growth_directory(self):
        outside = self.instance / "outside-growth"
        outside.mkdir()
        self.growth_dir().symlink_to(outside)

        result = self.run_workflow("validate")

        self.assertEqual(1, result.returncode)
        self.assertIn("growth 目录不能是 symlink", result.stderr)

    def test_validate_rejects_directly_edited_metric_records(self):
        publication_id, _publication_card = self.create_scheduled_publication()
        self.assertEqual(0, self.publish(publication_id).returncode)
        self.metric_catalog()
        self.assertEqual(
            0,
            self.record_metrics(publication_id, "48h", {"views": 1}).returncode,
        )
        metrics = self.publication_metrics_path(publication_id)
        record, text = parse_frontmatter(metrics)
        record["publication_id"] = "publication-20261105-120000000000-deadbeef"
        metrics.write_text(
            "---\n{}\n---{}".format(
                json.dumps(record, ensure_ascii=False, indent=2),
                text.split("---", 2)[2],
            ),
            encoding="utf-8",
        )

        wrong_id = self.run_workflow("validate")

        self.assertEqual(1, wrong_id.returncode)
        self.assertIn("publication_id 与固定目录名不一致", wrong_id.stderr)

        record["publication_id"] = publication_id
        record["snapshots"][0]["values"] = {"unknown": 1}
        metrics.write_text(
            "---\n{}\n---{}".format(
                json.dumps(record, ensure_ascii=False, indent=2),
                text.split("---", 2)[2],
            ),
            encoding="utf-8",
        )
        unknown = self.run_workflow("validate")

        self.assertEqual(1, unknown.returncode)
        self.assertIn("未注册", unknown.stderr)

    def test_reschedule_requires_parent_content_to_remain_ready(self):
        publication_id, _publication_card = self.create_scheduled_publication()
        publication_record, _ = parse_frontmatter(self.publication_cards()[0])
        content_id = publication_record["content_id"]
        self.main_draft(content_id).write_text(
            "# 主稿\n\n重新进入审核。\n",
            encoding="utf-8",
        )
        resubmitted = self.transition(
            content_id,
            "--to",
            "reviewing",
            actor="content",
        )
        self.assertEqual(0, resubmitted.returncode, resubmitted.stderr)
        invalid = self.run_workflow("validate")
        self.assertEqual(1, invalid.returncode)
        self.assertIn("ready", invalid.stderr)

        result = self.transition(
            publication_id,
            "--to",
            "scheduled",
            "--planned-at",
            "2026-11-22T10:30:00+08:00",
            "--timezone",
            "Asia/Shanghai",
            "--note",
            "配合活动窗口。",
            actor="gm",
        )

        self.assertEqual(1, result.returncode)
        self.assertIn("ready", result.stderr)

    def test_gm_cancels_before_publication_and_retains_record(self):
        publication_id, publication_card = self.create_scheduled_publication()

        result = self.transition(
            publication_id,
            "--to",
            "cancelled",
            "--note",
            "渠道计划调整。",
            actor="gm",
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue(publication_card.is_file())
        record, _ = parse_frontmatter(publication_card)
        self.assertEqual("cancelled", record["status"])
        self.assertEqual("2026-11-20T09:00:00+08:00", record["schedule"]["planned_at"])
        self.assertEqual("渠道计划调整。", record["cancellation"]["reason"])
        self.assertEqual("gm", record["cancellation"]["cancelled_by"])
        self.assertEqual("cancel", record["events"][-1]["action"])
        self.assertEqual("渠道计划调整。", record["events"][-1]["note"])
        self.assertEqual(0, self.run_workflow("validate").returncode)

    def test_validate_rejects_cancelled_record_without_cancellation_metadata(self):
        publication_id, publication_card = self.create_scheduled_publication()
        cancelled = self.transition(
            publication_id,
            "--to",
            "cancelled",
            "--note",
            "渠道计划调整。",
            actor="gm",
        )
        self.assertEqual(0, cancelled.returncode, cancelled.stderr)
        record, text = parse_frontmatter(publication_card)
        del record["cancellation"]
        body = text.split("---", 2)[2]
        publication_card.write_text(
            "---\n{}\n---{}".format(
                json.dumps(record, ensure_ascii=False, indent=2),
                body,
            ),
            encoding="utf-8",
        )

        result = self.run_workflow("validate")

        self.assertEqual(1, result.returncode)
        self.assertIn("cancellation", result.stderr)

    def test_validate_rejects_schedule_that_disagrees_with_latest_event(self):
        _publication_id, publication_card = self.create_scheduled_publication()
        record, text = parse_frontmatter(publication_card)
        record["schedule"]["planned_at"] = "2026-11-21T09:00:00+08:00"
        body = text.split("---", 2)[2]
        publication_card.write_text(
            "---\n{}\n---{}".format(
                json.dumps(record, ensure_ascii=False, indent=2),
                body,
            ),
            encoding="utf-8",
        )

        result = self.run_workflow("validate")

        self.assertEqual(1, result.returncode)
        self.assertIn("schedule 与排期 event 不一致", result.stderr)

    def test_reschedule_and_cancel_require_a_reason(self):
        publication_id, publication_card = self.create_scheduled_publication()
        before = publication_card.read_bytes()

        for arguments in (
            (
                "--to",
                "scheduled",
                "--planned-at",
                "2026-11-22T10:30:00+08:00",
                "--timezone",
                "Asia/Shanghai",
            ),
            ("--to", "cancelled"),
        ):
            with self.subTest(arguments=arguments):
                result = self.transition(publication_id, *arguments, actor="gm")
                self.assertEqual(1, result.returncode)
                self.assertIn("note", result.stderr)
                self.assertEqual(before, publication_card.read_bytes())

    def test_schedule_rejects_invalid_or_mismatched_timezone(self):
        content_id, _content_card = self.create_ready_content()
        publication_id, _publication_card = self.create_publication(content_id)
        self.publication_draft(publication_id).write_text("# 渠道稿\n", encoding="utf-8")
        self.assertEqual(
            0,
            self.transition(
                publication_id,
                "--to",
                "reviewing",
                actor="content",
            ).returncode,
        )
        self.assertEqual(
            0,
            self.transition(
                publication_id,
                "--decision",
                "approved",
                actor="gm",
            ).returncode,
        )

        for planned_at, timezone_name in (
            ("2026-11-20T09:00:00", "Asia/Shanghai"),
            ("2026-11-20T09:00:00+00:00", "Asia/Shanghai"),
            ("2026-11-20T09:00:00+08:00", "Mars/Olympus"),
        ):
            with self.subTest(planned_at=planned_at, timezone=timezone_name):
                result = self.transition(
                    publication_id,
                    "--to",
                    "scheduled",
                    "--planned-at",
                    planned_at,
                    "--timezone",
                    timezone_name,
                    actor="gm",
                )
                self.assertEqual(1, result.returncode)
                self.assertIn("timezone", result.stderr)

    def test_publication_changes_requested_returns_to_adapting(self):
        content_id, _content_card = self.create_ready_content()
        publication_id, publication_card = self.create_publication(content_id)
        self.assertEqual(
            0,
            self.transition(
                publication_id,
                "--to",
                "reviewing",
                actor="content",
            ).returncode,
        )

        result = self.transition(
            publication_id,
            "--decision",
            "changes_requested",
            "--note",
            "补齐渠道 CTA。",
            actor="gm",
        )

        self.assertEqual(0, result.returncode, result.stderr)
        record, _ = parse_frontmatter(publication_card)
        self.assertEqual("adapting", record["status"])
        self.assertEqual("changes_requested", record["approval"]["status"])
        self.publication_draft(publication_id).write_text(
            "# 渠道稿\n\n补齐 CTA。\n",
            encoding="utf-8",
        )
        self.assertEqual(0, self.run_workflow("validate").returncode)

    # ---------- content transition / approval ----------

    def test_transition_rejects_symlink_content_root_without_writing_target(self):
        content_id = "content-20261105-120000000000-a1b2c3d4"
        outside = Path(self.temp.name + "-outside-transition")
        package = outside / content_id
        package.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, outside, True)
        record = self.valid_record(content_id)
        card = package / "内容卡.md"
        card.write_text(
            "---\n{}\n---\n\n# 内容卡\n".format(
                json.dumps(record, ensure_ascii=False, indent=2)
            ),
            encoding="utf-8",
        )
        content_root = self.instance / "knowledge" / "content"
        try:
            content_root.symlink_to(outside, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"当前平台无法创建 symlink：{error}")
        before = card.read_bytes()

        result = self.transition(content_id, "--to", "drafting", actor="content")

        self.assertEqual(1, result.returncode)
        self.assertIn("symlink", result.stderr)
        self.assertEqual(before, card.read_bytes())
        self.assertFalse((package / "主稿.md").exists())

    def test_normal_review_flow_keeps_main_draft_fixed_and_reaches_ready(self):
        content_id, card = self.create_content(target_date="2026-11-20")

        drafting = self.transition(content_id, "--to", "drafting", actor="content")
        self.assertEqual(0, drafting.returncode, drafting.stderr)
        draft = self.main_draft(content_id)
        self.assertTrue(draft.is_file())
        self.assertEqual(card.parent, draft.parent)
        record, _ = parse_frontmatter(card)
        self.assertEqual("drafting", record["status"])
        self.assertEqual("主稿.md", record["main_draft"])
        self.assertNotIn("approval", record)
        self.assertEqual("transition", record["events"][-1]["action"])

        body = "# 第一版主稿\n\n正文内容。\n"
        draft.write_text(body, encoding="utf-8")
        reviewing = self.transition(content_id, "--to", "reviewing", actor="content")
        self.assertEqual(0, reviewing.returncode, reviewing.stderr)
        record, _ = parse_frontmatter(card)
        expected_hash = "sha256:" + hashlib.sha256(body.encode()).hexdigest()
        self.assertEqual("reviewing", record["status"])
        self.assertEqual(
            {
                "status": "pending",
                "requested_at": record["approval"]["requested_at"],
                "requested_by": "content",
                "artifact": "主稿.md",
                "artifact_hash": expected_hash,
            },
            record["approval"],
        )
        self.assertEqual("submit_review", record["events"][-1]["action"])

        approved = self.transition(
            content_id,
            "--decision",
            "approved",
            "--note",
            "owner 已确认。",
            actor="gm",
        )
        self.assertEqual(0, approved.returncode, approved.stderr)
        record, _ = parse_frontmatter(card)
        self.assertEqual("ready", record["status"])
        self.assertEqual("approved", record["approval"]["status"])
        self.assertEqual("gm", record["approval"]["decided_by"])
        self.assertEqual(expected_hash, record["approval"]["artifact_hash"])
        self.assertEqual("approval_decision", record["events"][-1]["action"])
        self.assertEqual("approved", record["events"][-1]["decision"])
        self.assertEqual(0, self.run_workflow("validate").returncode)

    def test_content_requests_review_and_gm_records_decisions(self):
        content_id, _card = self.create_content()
        wrong_drafter = self.transition(content_id, "--to", "drafting", actor="gm")
        self.assertEqual(1, wrong_drafter.returncode)
        self.assertIn("content", wrong_drafter.stderr)

        self.assertEqual(
            0,
            self.transition(content_id, "--to", "drafting", actor="content").returncode,
        )
        wrong_reviewer = self.transition(content_id, "--to", "reviewing", actor="gm")
        self.assertEqual(1, wrong_reviewer.returncode)
        self.assertIn("content", wrong_reviewer.stderr)

        self.main_draft(content_id).write_text("# 主稿\n", encoding="utf-8")
        self.assertEqual(
            0,
            self.transition(content_id, "--to", "reviewing", actor="content").returncode,
        )
        wrong_decider = self.transition(
            content_id,
            "--decision",
            "approved",
            actor="content",
        )
        self.assertEqual(1, wrong_decider.returncode)
        self.assertIn("gm", wrong_decider.stderr)

    def test_ready_cannot_be_entered_without_approved_review(self):
        content_id, _card = self.create_content()
        self.assertEqual(
            0,
            self.transition(content_id, "--to", "drafting", actor="content").returncode,
        )

        result = self.transition(content_id, "--to", "ready", actor="content")

        self.assertEqual(1, result.returncode)
        self.assertIn("approved", result.stderr)

    def test_changes_requested_and_rejected_return_to_drafting_with_note(self):
        for decision in ("changes_requested", "rejected"):
            with self.subTest(decision=decision):
                content_id, card = self.create_content(title=decision)
                self.advance_to_reviewing(content_id)

                result = self.transition(
                    content_id,
                    "--decision",
                    decision,
                    "--note",
                    "请补充证据。",
                    actor="gm",
                )

                self.assertEqual(0, result.returncode, result.stderr)
                record, _ = parse_frontmatter(card)
                self.assertEqual("drafting", record["status"])
                self.assertEqual(decision, record["approval"]["status"])
                self.assertEqual("请补充证据。", record["approval"]["note"])
                self.assertEqual(decision, record["events"][-1]["decision"])

    def test_non_approved_decision_requires_a_note(self):
        content_id, _card = self.create_content()
        self.advance_to_reviewing(content_id)

        result = self.transition(
            content_id,
            "--decision",
            "changes_requested",
            actor="gm",
        )

        self.assertEqual(1, result.returncode)
        self.assertIn("note", result.stderr)

    def test_edit_after_changes_requested_is_valid_drafting_work(self):
        content_id, _card = self.create_content()
        draft = self.advance_to_reviewing(content_id)
        returned = self.transition(
            content_id,
            "--decision",
            "changes_requested",
            "--note",
            "请补充证据。",
            actor="gm",
        )
        self.assertEqual(0, returned.returncode, returned.stderr)

        draft.write_text("# 主稿\n\n按反馈修改。\n", encoding="utf-8")

        validated = self.run_workflow("validate")
        built = self.run_workflow("build")
        self.assertEqual(0, validated.returncode, validated.stderr)
        self.assertEqual(0, built.returncode, built.stderr)

    def test_edit_after_approval_is_stale_and_reapproval_keeps_history(self):
        content_id, card = self.create_content()
        draft = self.advance_to_reviewing(content_id)
        approved = self.transition(content_id, "--decision", "approved", actor="gm")
        self.assertEqual(0, approved.returncode, approved.stderr)
        before_edit, _ = parse_frontmatter(card)
        event_count = len(before_edit["events"])
        first_hash = before_edit["approval"]["artifact_hash"]
        built = self.run_workflow("build")
        self.assertEqual(0, built.returncode, built.stderr)
        calendar = self.instance / "knowledge" / "business" / "选题日历.md"
        previous_calendar = calendar.read_bytes()

        draft.write_text("# 主稿\n\n审批后的修改。\n", encoding="utf-8")
        stale = self.run_workflow("validate")
        self.assertEqual(1, stale.returncode)
        self.assertIn("stale approval", stale.stderr)
        stale_build = self.run_workflow("build")
        self.assertEqual(1, stale_build.returncode)
        self.assertIn("stale approval", stale_build.stderr)
        self.assertEqual(previous_calendar, calendar.read_bytes())
        after_edit, _ = parse_frontmatter(card)
        self.assertEqual(event_count, len(after_edit["events"]), "普通文案编辑不产生业务事件")

        resubmit = self.transition(content_id, "--to", "reviewing", actor="content")
        self.assertEqual(0, resubmit.returncode, resubmit.stderr)
        reapproved = self.transition(content_id, "--decision", "approved", actor="gm")
        self.assertEqual(0, reapproved.returncode, reapproved.stderr)
        final, _ = parse_frontmatter(card)
        self.assertEqual("ready", final["status"])
        self.assertNotEqual(first_hash, final["approval"]["artifact_hash"])
        decisions = [
            event
            for event in final["events"]
            if event["action"] == "approval_decision"
        ]
        self.assertEqual(2, len(decisions))
        self.assertEqual(first_hash, decisions[0]["artifact_hash"])
        self.assertEqual(0, self.run_workflow("validate").returncode)

    def test_decision_refuses_a_draft_changed_after_review_request(self):
        content_id, card = self.create_content()
        draft = self.advance_to_reviewing(content_id)
        before, _ = parse_frontmatter(card)
        draft.write_text("# 主稿\n\n请求审核后又改了。\n", encoding="utf-8")

        result = self.transition(content_id, "--decision", "approved", actor="gm")

        self.assertEqual(1, result.returncode)
        self.assertIn("stale approval", result.stderr)
        after, _ = parse_frontmatter(card)
        self.assertEqual(before, after)

    # ---------- validate ----------

    def test_validate_accepts_an_empty_instance(self):
        result = self.run_workflow("validate")

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("校验通过：0 条内容记录", result.stdout)

    def test_validate_reads_a_valid_manually_edited_card(self):
        content_id = "content-20261105-120000000000-a1b2c3d4"
        self.write_card(content_id, self.valid_record(content_id))

        result = self.run_workflow("validate")

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("校验通过：1 条内容记录", result.stdout)

    def test_validate_reports_malformed_frontmatter_with_source_path(self):
        content_id = "content-20261105-120000000000-a1b2c3d4"
        self.write_card(content_id, raw_frontmatter='{ "schema_version": 1,')

        result = self.run_workflow("validate")

        self.assertEqual(1, result.returncode)
        self.assertIn(f"knowledge/content/{content_id}/内容卡.md", result.stderr)
        self.assertIn("frontmatter 不是合法 JSON", result.stderr)

    def test_validate_rejects_wrong_field_types_including_bool_schema(self):
        mutations = {
            "schema_version": True,
            "record_type": ["content"],
            "content_id": 42,
            "title": ["标题"],
            "status": {"value": "proposed"},
            "created_at": 123,
            "actor": ["content"],
            "events": {"action": "create"},
            "source": ["访谈"],
            "summary": {"text": "摘要"},
        }
        for field, value in mutations.items():
            with self.subTest(field=field):
                content_id = "content-20261105-120000000000-a1b2c3d4"
                record = self.valid_record(content_id)
                record[field] = value
                self.write_card(content_id, record)

                result = self.run_workflow("validate")

                self.assertEqual(1, result.returncode)
                self.assertIn(f"字段 {field}", result.stderr)
                self.assertIn(f"knowledge/content/{content_id}/内容卡.md", result.stderr)
                (self.instance / "knowledge" / "content" / content_id / "内容卡.md").unlink()

    def test_validate_rejects_unknown_schema_version(self):
        content_id = "content-20261105-120000000000-a1b2c3d4"
        record = self.valid_record(content_id)
        record["schema_version"] = 2
        self.write_card(content_id, record)

        result = self.run_workflow("validate")

        self.assertEqual(1, result.returncode)
        self.assertIn("未知 schema_version：2", result.stderr)
        self.assertIn(f"knowledge/content/{content_id}/内容卡.md", result.stderr)

    def test_validate_reports_duplicate_ids_and_both_source_records(self):
        content_id = "content-20261105-120000000000-a1b2c3d4"
        other_directory = "content-20261105-120000000001-a1b2c3d4"
        self.write_card(content_id, self.valid_record(content_id))
        self.write_card(other_directory, self.valid_record(content_id))

        result = self.run_workflow("validate")

        self.assertEqual(1, result.returncode)
        self.assertIn("重复 content_id", result.stderr)
        self.assertIn(f"knowledge/content/{content_id}/内容卡.md", result.stderr)
        self.assertIn(f"knowledge/content/{other_directory}/内容卡.md", result.stderr)

    def test_validate_rejects_unknown_actor(self):
        content_id = "content-20261105-120000000000-a1b2c3d4"
        record = self.valid_record(content_id)
        record["actor"] = "researcher"
        record["events"][0]["actor"] = "researcher"
        self.write_card(content_id, record)

        result = self.run_workflow("validate")

        self.assertEqual(1, result.returncode)
        self.assertIn("非法 actor「researcher」", result.stderr)
        self.assertIn(f"knowledge/content/{content_id}/内容卡.md", result.stderr)

    def test_validate_rejects_naive_and_invalid_times(self):
        for value in ("2026-11-05T12:00:00", "not-a-time"):
            with self.subTest(value=value):
                content_id = "content-20261105-120000000000-a1b2c3d4"
                record = self.valid_record(content_id)
                record["created_at"] = value
                record["events"][0]["at"] = value
                self.write_card(content_id, record)

                result = self.run_workflow("validate")

                self.assertEqual(1, result.returncode)
                self.assertIn("offset-aware ISO 8601", result.stderr)
                self.assertIn(f"knowledge/content/{content_id}/内容卡.md", result.stderr)
                (self.instance / "knowledge" / "content" / content_id / "内容卡.md").unlink()

    def test_validate_rejects_content_id_that_does_not_match_fixed_path(self):
        directory_id = "content-20261105-120000000001-a1b2c3d4"
        record_id = "content-20261105-120000000000-a1b2c3d4"
        self.write_card(directory_id, self.valid_record(record_id))

        result = self.run_workflow("validate")

        self.assertEqual(1, result.returncode)
        self.assertIn("与固定目录名不一致", result.stderr)
        self.assertIn(f"knowledge/content/{directory_id}/内容卡.md", result.stderr)

    def test_validate_accepts_a_card_with_later_business_events(self):
        content_id = "content-20261105-120000000000-a1b2c3d4"
        record = self.valid_record(content_id)
        record["status"] = "drafting"
        record["main_draft"] = "主稿.md"
        record["events"].append(
            {
                "action": "transition",
                "at": "2026-11-06T09:00:00+00:00",
                "actor": "content",
                "from_status": "proposed",
                "to_status": "drafting",
            }
        )
        card = self.write_card(content_id, record)
        (card.parent / "主稿.md").write_text("# 主稿\n", encoding="utf-8")

        result = self.run_workflow("validate")

        self.assertEqual(0, result.returncode, result.stderr)

    def test_validate_rejects_a_broken_event_state_chain(self):
        content_id = "content-20261105-120000000000-a1b2c3d4"
        record = self.valid_record(content_id)
        record["status"] = "drafting"
        record["main_draft"] = "主稿.md"
        record["events"].append(
            {
                "action": "transition",
                "at": "2026-11-06T09:00:00+00:00",
                "actor": "content",
                "from_status": "ready",
                "to_status": "drafting",
            }
        )
        card = self.write_card(content_id, record)
        (card.parent / "主稿.md").write_text("# 主稿\n", encoding="utf-8")

        result = self.run_workflow("validate")

        self.assertEqual(1, result.returncode)
        self.assertIn("事件状态链", result.stderr)

    def test_validate_rejects_wrong_business_actor_in_review_event(self):
        content_id, card = self.create_content()
        self.advance_to_reviewing(content_id)
        record, text = parse_frontmatter(card)
        record["events"][-1]["actor"] = "gm"
        body = text.split("---", 2)[2]
        card.write_text(
            "---\n{}\n---{}".format(
                json.dumps(record, ensure_ascii=False, indent=2),
                body,
            ),
            encoding="utf-8",
        )

        result = self.run_workflow("validate")

        self.assertEqual(1, result.returncode)
        self.assertIn("submit_review actor 必须是 content", result.stderr)

    def test_validate_rejects_approval_that_disagrees_with_review_event(self):
        content_id, card = self.create_content()
        self.advance_to_reviewing(content_id)
        record, text = parse_frontmatter(card)
        record["events"][-1]["artifact_hash"] = "sha256:" + "0" * 64
        body = text.split("---", 2)[2]
        card.write_text(
            "---\n{}\n---{}".format(
                json.dumps(record, ensure_ascii=False, indent=2),
                body,
            ),
            encoding="utf-8",
        )

        result = self.run_workflow("validate")

        self.assertEqual(1, result.returncode)
        self.assertIn("approval 与 submit_review event 不一致", result.stderr)

    def test_validate_rejects_an_unknown_status(self):
        content_id = "content-20261105-120000000000-a1b2c3d4"
        record = self.valid_record(content_id)
        record["status"] = "随便写的状态"
        self.write_card(content_id, record)

        result = self.run_workflow("validate")

        self.assertEqual(1, result.returncode)
        self.assertIn("未知 status", result.stderr)
        self.assertIn(f"knowledge/content/{content_id}/内容卡.md", result.stderr)

    def test_validate_rejects_an_event_with_a_bad_timestamp(self):
        content_id = "content-20261105-120000000000-a1b2c3d4"
        record = self.valid_record(content_id)
        record["events"].append(
            {
                "action": "accept",
                "at": "2026-11-06 09:00:00",
                "actor": "gm",
                "to_status": "drafting",
            }
        )
        self.write_card(content_id, record)

        result = self.run_workflow("validate")

        self.assertEqual(1, result.returncode)
        self.assertIn("offset-aware ISO 8601", result.stderr)
        self.assertIn(f"knowledge/content/{content_id}/内容卡.md", result.stderr)

    def test_validate_warns_about_a_package_without_a_card_without_blocking(self):
        package = self.instance / "knowledge" / "content" / "content-20261105-120000000000-a1b2c3d4"
        package.mkdir(parents=True)

        result = self.run_workflow("validate")

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("警告", result.stdout)
        self.assertIn("缺少内容卡", result.stdout)

    def test_create_content_rejects_symlink_content_root_without_writing_target(self):
        outside = Path(self.temp.name + "-outside-create")
        outside.mkdir()
        self.addCleanup(shutil.rmtree, outside, True)
        content_root = self.instance / "knowledge" / "content"
        try:
            content_root.symlink_to(outside, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"当前平台无法创建 symlink：{error}")

        result = self.run_workflow("create-content", "--title", "不得越界")

        self.assertEqual(1, result.returncode)
        self.assertIn("symlink", result.stderr)
        self.assertEqual([], list(outside.iterdir()))

    def test_validate_rejects_symlink_content_package_without_reading_target(self):
        content_root = self.instance / "knowledge" / "content"
        content_root.mkdir(parents=True)
        outside = Path(self.temp.name + "-outside")
        outside.mkdir()
        self.addCleanup(lambda: outside.rmdir() if outside.exists() else None)
        try:
            (content_root / "linked").symlink_to(outside, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"当前平台无法创建 symlink：{error}")

        result = self.run_workflow("validate")

        self.assertEqual(1, result.returncode)
        self.assertIn("knowledge/content/linked", result.stderr)
        self.assertIn("symlink", result.stderr)

    # ---------- dashboard contract ----------

    def test_build_writes_versioned_dashboard_json_with_metadata_only(self):
        publication_id, _publication_card = self.create_published_publication()
        self.metric_catalog()
        self.assertEqual(
            0,
            self.record_metrics(publication_id, "48h", {"views": 1234}).returncode,
        )
        self.write_inbox(
            "gm",
            [
                "- [2026-11-04 09:30] 发起方：gm | 任务：产出本周选题清单 | 验收：10 个选题",
                "- ✅ [2026-11-03 08:00] 发起方：gm | 任务：修掉旧日历 | 验收：已删除",
            ],
        )
        self.write_team(["| gm | `opc-gm` | `opc-gm` | claude | `knowledge/inbox/gm.md` |"])

        result = self.run_workflow("build")

        self.assertEqual(0, result.returncode, result.stderr)
        payload = self.dashboard()
        self.assertEqual(1, payload["contract_version"])
        self.assertTrue(payload["generated"])
        self.assertTrue(payload["read_only"])
        self.assertEqual(1, payload["counts"]["contents"])
        self.assertEqual(1, payload["counts"]["publications"])
        self.assertEqual(2, payload["counts"]["tasks"])

        content = payload["contents"][0]
        self.assertEqual("ready", content["status"])
        self.assertEqual("content", content["role"])
        self.assertEqual([publication_id], content["publication_ids"])
        self.assertIn("status", content)
        for field in ("priority", "blocked", "target_date", "created_at"):
            self.assertIn(field, content)

        publication = payload["publications"][0]
        self.assertEqual(publication_id, publication["publication_id"])
        self.assertEqual("published", publication["status"])
        self.assertEqual("2026-11-20T09:07:00+08:00", publication["published_at"])
        self.assertEqual("https://example.com/posts/launch", publication["url"])
        self.assertEqual("48h", publication["metrics"]["windows"][0]["window"])
        self.assertIn("source_path", publication)
        self.assertIn("draft_path", publication)

        tasks = payload["tasks"]
        self.assertEqual(["open", "done"], [task["state"] for task in tasks])
        self.assertEqual("gm", tasks[0]["role"])
        self.assertTrue(tasks[0]["task_id"].startswith("task-"))
        self.assertEqual("产出本周选题清单", tasks[0]["task"])
        self.assertEqual("10 个选题", tasks[0]["acceptance"])

        self.assertEqual(
            [{"role": "gm", "terminal": "opc-gm"}],
            payload["team"],
        )

        text = self.dashboard_path().read_text(encoding="utf-8")
        self.assertNotIn("已完成适配", text)
        self.assertNotIn("第一版正文", text)
        self.assertNotIn("artifact_hash", text)

    def test_build_dashboard_for_empty_instance_is_valid_and_renderable(self):
        result = self.run_workflow("build")

        self.assertEqual(0, result.returncode, result.stderr)
        payload = self.dashboard()
        self.assertEqual(1, payload["contract_version"])
        self.assertEqual([], payload["contents"])
        self.assertEqual([], payload["publications"])
        self.assertEqual([], payload["tasks"])
        self.assertEqual([], payload["approvals"])
        self.assertEqual(0, payload["counts"]["contents"])

    def test_build_dashboard_keeps_last_valid_cache_when_validation_fails(self):
        publication_id, _publication_card = self.create_published_publication()
        self.assertEqual(0, self.run_workflow("build").returncode)
        previous = self.dashboard_path().read_bytes()

        content_id, card = self.create_content(title="会被写坏的卡")
        card.write_text("---\nnot-json\n---\n\n# 内容卡\n", encoding="utf-8")

        result = self.run_workflow("build")

        self.assertEqual(1, result.returncode)
        self.assertEqual(previous, self.dashboard_path().read_bytes())

    def test_build_dashboard_is_deterministic(self):
        publication_id, _publication_card = self.create_published_publication()
        self.metric_catalog()
        self.assertEqual(
            0,
            self.record_metrics(publication_id, "48h", {"views": 1234}).returncode,
        )

        first = self.run_workflow("build")
        self.assertEqual(0, first.returncode, first.stderr)
        first_bytes = self.dashboard_path().read_bytes()
        second = self.run_workflow("build")
        self.assertEqual(0, second.returncode, second.stderr)

        self.assertEqual(first_bytes, self.dashboard_path().read_bytes())

    def test_build_dashboard_exposes_default_scope_and_filter_fields(self):
        publication_id, _publication_card = self.create_published_publication()
        self.write_inbox(
            "gm",
            ["- [2026-11-04 09:30] 发起方：gm | 任务：跟进发布 | 验收：已确认"],
        )

        self.assertEqual(0, self.run_workflow("build").returncode)
        payload = self.dashboard()

        scope = payload["scope"]
        self.assertEqual([publication_id], scope["publication_ids"])
        self.assertEqual(
            [record["content_id"] for record in payload["contents"]],
            scope["content_ids"],
        )
        self.assertEqual(1, len(scope["task_ids"]))
        publication = payload["publications"][0]
        for field in ("channel", "status", "role", "priority", "blocked"):
            self.assertIn(field, publication)
        self.assertIn("as_of", payload)

    def test_build_dashboard_reports_warnings_without_blocking(self):
        publication_id, _publication_card = self.create_published_publication()
        self.metric_catalog()

        result = self.run_workflow("build")

        self.assertEqual(0, result.returncode, result.stderr)
        payload = self.dashboard()
        self.assertEqual([], payload["diagnostics"]["errors"])
        self.assertTrue(payload["diagnostics"]["warnings"])
        self.assertTrue(payload["publications"][0]["needs_metrics"])

    def test_build_dashboard_keeps_account_level_metrics_out_of_publications(self):
        publication_id, _publication_card = self.create_published_publication()
        self.metric_catalog()
        self.assertEqual(
            0,
            self.record_metrics(publication_id, "48h", {"views": 1234}).returncode,
        )
        self.assertEqual(0, self.record_channel_snapshot({"followers": 5000}).returncode)

        self.assertEqual(0, self.run_workflow("build").returncode)
        payload = self.dashboard()

        publication = payload["publications"][0]
        self.assertNotIn("followers", json.dumps(publication, ensure_ascii=False))
        channels = payload["channels"]
        self.assertEqual("wechat", channels[0]["channel"])
        self.assertEqual(5000, channels[0]["account_metrics"]["followers"])

    def test_build_dashboard_surfaces_recorded_review_conclusion(self):
        publication_id, _publication_card = self.create_published_publication()
        reviewed = self.transition(
            publication_id,
            "--to",
            "reviewed",
            "--conclusion",
            "continue",
            "--next-action",
            "按同一形式扩量",
            actor="growth",
        )
        self.assertEqual(0, reviewed.returncode, reviewed.stderr)

        result = self.run_workflow("build")
        self.assertEqual(0, result.returncode, result.stderr)
        payload = self.dashboard()

        publication = payload["publications"][0]
        self.assertFalse(publication["needs_review"])
        self.assertEqual("done", publication["review"]["status"])
        self.assertEqual("continue", publication["review"]["conclusion"])
        self.assertIsNotNone(publication["review"]["recorded_at"])
        # 近期发布、没有待办指标的 publication 仍在默认范围内。
        self.assertIn(publication_id, payload["scope"]["publication_ids"])

    def test_build_dashboard_lists_pending_approvals(self):
        content_id, _content_card = self.create_ready_content()
        publication_id, _publication_card = self.create_publication(content_id)
        self.publication_draft(publication_id).write_text("# 渠道稿\n\n适配稿。\n", encoding="utf-8")
        reviewed = self.transition(
            publication_id,
            "--to",
            "reviewing",
            actor="content",
        )
        self.assertEqual(0, reviewed.returncode, reviewed.stderr)

        self.assertEqual(0, self.run_workflow("build").returncode)
        payload = self.dashboard()

        approvals = payload["approvals"]
        self.assertEqual(1, len(approvals))
        self.assertEqual("publication", approvals[0]["entity"])
        self.assertEqual(publication_id, approvals[0]["id"])
        self.assertEqual("渠道稿.md", approvals[0]["artifact"])
        self.assertIn(publication_id, payload["scope"]["publication_ids"])

    def test_inbox_uses_stable_task_id_reference_and_skips_examples(self):
        content_id, _content_card = self.create_ready_content()
        self.write_inbox(
            "gm",
            [
                "```",
                "- [YYYY-MM-DD HH:MM] 发起方：<角色> | 任务：<做什么> | 验收：<怎么算完成>",
                "```",
                "- [2026-12-01 09:30] 发起方：gm | 任务 ID：task-abc123 | 业务引用：{} | "
                "任务：跟进复盘 | 验收：有结论".format(content_id),
            ],
        )
        self.write_team(["| gm | `opc-gm` | `opc-gm` | claude | `knowledge/inbox/gm.md` |"])

        result = self.run_workflow("build")

        self.assertEqual(0, result.returncode, result.stderr)
        tasks = self.dashboard()["tasks"]
        self.assertEqual(1, len(tasks), "围栏代码块里的示例不是待办")
        self.assertEqual("task-abc123", tasks[0]["task_id"])
        self.assertEqual(content_id, tasks[0]["reference"])

    def test_build_dashboard_reads_inbox_states_from_markers(self):
        self.write_inbox(
            "gm",
            [
                "- [2026-11-04 09:30] 发起方：gm | 任务：产出本周选题清单 | 验收：10 个选题",
                "- ✅ [2026-11-03 08:00] 发起方：gm | 任务：修掉旧日历 | 验收：已删除",
                "- ⛔ 已撤销：不再需要 - [2026-11-02 08:00] 发起方：gm | 任务：换个方向 | 验收：无",
            ],
        )

        self.assertEqual(0, self.run_workflow("build").returncode)
        payload = self.dashboard()

        self.assertEqual(
            ["open", "done", "cancelled"],
            [task["state"] for task in payload["tasks"]],
        )
        self.assertEqual("不再需要", payload["tasks"][2]["reason"])
        self.assertEqual(
            [payload["tasks"][0]["task_id"]],
            payload["scope"]["task_ids"],
        )

    def test_end_to_end_dashboard_covers_content_publish_metrics_and_tasks(self):
        publication_id, _publication_card = self.create_published_publication()
        self.metric_catalog()
        self.assertEqual(
            0,
            self.record_metrics(publication_id, "48h", {"views": 1234}).returncode,
        )
        self.write_inbox(
            "content",
            ["- [2026-11-04 09:30] 发起方：gm | 任务：产出本周选题清单 | 验收：10 个选题"],
        )
        self.write_team(["| gm | `opc-gm` | `opc-gm` | claude | `knowledge/inbox/gm.md` |"])

        self.assertEqual(0, self.run_workflow("build").returncode)
        payload = self.dashboard()

        content = payload["contents"][0]
        self.assertEqual("ready", content["status"])
        self.assertEqual([publication_id], content["publication_ids"])

        publication = payload["publications"][0]
        self.assertEqual("published", publication["status"])
        self.assertEqual("48h", publication["metrics"]["windows"][0]["window"])
        self.assertIn("views=1234", publication["metrics"]["summary"])
        self.assertTrue(
            publication["source_path"].endswith("发布卡.md"),
            publication["source_path"],
        )
        self.assertTrue(
            publication["metrics_path"].endswith("指标.md"),
            publication["metrics_path"],
        )

        self.assertEqual(1, payload["counts"]["tasks"])
        self.assertEqual("产出本周选题清单", payload["tasks"][0]["task"])
        self.assertEqual([{"role": "gm", "terminal": "opc-gm"}], payload["team"])
        self.assertEqual([], payload["diagnostics"]["errors"])
        self.assertIn(content["content_id"], payload["scope"]["content_ids"])
        self.assertIn(publication_id, payload["scope"]["publication_ids"])

    # ---------- publication review and content close ----------

    def test_publication_declares_required_windows_and_optional_flag(self):
        content_id, _card = self.create_ready_content()

        required = self.run_workflow(
            "create-publication",
            content_id,
            "--channel",
            "wechat",
            "--required-window",
            "48h",
            "--required-window",
            "7d",
            "--actor",
            "gm",
        )
        self.assertEqual(0, required.returncode, required.stderr)
        required_record, _ = parse_frontmatter(self.publication_cards()[-1])
        self.assertTrue(required_record["required"])
        self.assertEqual(["48h", "7d"], required_record["required_metric_windows"])

        optional = self.run_workflow(
            "create-publication",
            content_id,
            "--channel",
            "wechat",
            "--optional",
            "--actor",
            "gm",
        )
        self.assertEqual(0, optional.returncode, optional.stderr)
        optional_record, _ = parse_frontmatter(self.publication_cards()[-1])
        self.assertFalse(optional_record["required"])
        self.assertEqual([], optional_record["required_metric_windows"])

    def test_growth_reviews_publication_after_required_windows_exist(self):
        publication_id, publication_card = self.create_published_publication()
        record, _ = parse_frontmatter(publication_card)
        record["required_metric_windows"] = ["48h"]
        write_frontmatter(publication_card, record)
        self.metric_catalog()
        metric_result = self.record_metrics(publication_id, "48h", {"views": 1234})
        self.assertEqual(0, metric_result.returncode, metric_result.stderr)

        reviewed = self.transition(
            publication_id,
            "--to",
            "reviewed",
            "--conclusion",
            "iterate",
            "--next-action",
            "优化标题后复用",
            actor="growth",
        )

        self.assertEqual(0, reviewed.returncode, reviewed.stderr)
        final, _ = parse_frontmatter(publication_card)
        self.assertEqual("reviewed", final["status"])
        self.assertEqual("iterate", final["review"]["conclusion"])
        self.assertEqual("优化标题后复用", final["review"]["next_action"])
        self.assertEqual(["48h"], final["review"]["metric_windows"])
        self.assertEqual("growth", final["review"]["recorded_by"])

    def test_review_rejects_missing_required_window(self):
        publication_id, publication_card = self.create_published_publication()
        record, _ = parse_frontmatter(publication_card)
        record["required_metric_windows"] = ["48h", "7d"]
        write_frontmatter(publication_card, record)
        self.metric_catalog()
        self.assertEqual(
            0,
            self.record_metrics(publication_id, "48h", {"views": 1234}).returncode,
        )

        reviewed = self.transition(
            publication_id,
            "--to",
            "reviewed",
            "--conclusion",
            "inconclusive",
            "--next-action",
            "等待 7d 数据",
            actor="growth",
        )

        self.assertEqual(1, reviewed.returncode)
        self.assertIn("7d", reviewed.stderr)
        final, _ = parse_frontmatter(publication_card)
        self.assertEqual("published", final["status"])

    def test_gm_reviews_with_explicit_data_exception(self):
        publication_id, publication_card = self.create_published_publication()
        record, _ = parse_frontmatter(publication_card)
        record["required_metric_windows"] = ["48h"]
        write_frontmatter(publication_card, record)

        reviewed = self.transition(
            publication_id,
            "--to",
            "reviewed",
            "--conclusion",
            "inconclusive",
            "--next-action",
            "改用平台导出的月报",
            "--exception-reason",
            "平台接口未提供历史窗口",
            actor="gm",
        )

        self.assertEqual(0, reviewed.returncode, reviewed.stderr)
        final, _ = parse_frontmatter(publication_card)
        self.assertEqual("reviewed", final["status"])
        self.assertEqual("平台接口未提供历史窗口", final["review"]["exception_reason"])
        event = final["events"][-1]
        self.assertEqual("review", event["action"])
        self.assertEqual("平台接口未提供历史窗口", event["exception_reason"])

    def test_content_close_lists_required_publication_blockers(self):
        content_id, content_card = self.create_ready_content()
        publication_id, _publication_card = self.create_publication(content_id)

        closed = self.transition(content_id, "--to", "closed", actor="gm")

        self.assertEqual(1, closed.returncode)
        self.assertIn(publication_id, closed.stderr)
        self.assertIn("adapting", closed.stderr)
        record, _ = parse_frontmatter(content_card)
        self.assertEqual("ready", record["status"])

    def test_content_closes_when_required_are_done_and_optional_does_not_block(self):
        content_id, content_card = self.create_ready_content()
        required_id, required_card = self.create_publication(content_id)
        optional_id, optional_card = self.create_publication(content_id)

        required_record, _ = parse_frontmatter(required_card)
        required_record["status"] = "cancelled"
        required_record["cancellation"] = {
            "cancelled_at": "2026-11-21T10:00:00+08:00",
            "cancelled_by": "gm",
            "reason": "渠道临时停更",
        }
        required_record["events"].append(
            {
                "action": "cancel",
                "at": "2026-11-21T10:00:00+08:00",
                "actor": "gm",
                "from_status": "adapting",
                "to_status": "cancelled",
                "note": "渠道临时停更",
            }
        )
        write_frontmatter(required_card, required_record)
        optional_record, _ = parse_frontmatter(optional_card)
        optional_record["required"] = False
        write_frontmatter(optional_card, optional_record)

        closed = self.transition(content_id, "--to", "closed", actor="gm")

        self.assertEqual(0, closed.returncode, closed.stderr)
        final, _ = parse_frontmatter(content_card)
        self.assertEqual("closed", final["status"])
        self.assertEqual("close", final["events"][-1]["action"])
        self.assertEqual(required_id, required_record["publication_id"])
        self.assertEqual(optional_id, optional_record["publication_id"])

    def test_gm_cancels_proposed_content_with_reason(self):
        content_id, content_card = self.create_content(title="要取消的选题")

        cancelled = self.transition(
            content_id,
            "--to",
            "cancelled",
            "--note",
            "选题不再做",
            actor="gm",
        )

        self.assertEqual(0, cancelled.returncode, cancelled.stderr)
        record, _ = parse_frontmatter(content_card)
        self.assertEqual("cancelled", record["status"])
        self.assertEqual("gm", record["cancellation"]["cancelled_by"])
        self.assertEqual("选题不再做", record["cancellation"]["reason"])
        event = record["events"][-1]
        self.assertEqual("cancel", event["action"])
        self.assertEqual("gm", event["actor"])
        self.assertEqual("proposed", event["from_status"])
        self.assertEqual("cancelled", event["to_status"])
        self.assertEqual("选题不再做", event["note"])

    def test_content_cancel_requires_gm_reason_and_an_open_content(self):
        content_id, content_card = self.create_content(title="取消权限")

        not_gm = self.transition(
            content_id, "--to", "cancelled", "--note", "越权", actor="content"
        )
        self.assertEqual(1, not_gm.returncode)
        self.assertIn("gm", not_gm.stderr)

        no_reason = self.transition(content_id, "--to", "cancelled", actor="gm")
        self.assertEqual(1, no_reason.returncode)
        self.assertIn("note", no_reason.stderr)

        record, _ = parse_frontmatter(content_card)
        self.assertEqual("proposed", record["status"])

        ready_id, _ready_card = self.create_ready_content(title="已就绪")
        not_open = self.transition(
            ready_id, "--to", "cancelled", "--note", "已就绪", actor="gm"
        )
        self.assertEqual(1, not_open.returncode)

    def test_cancelled_content_is_terminal(self):
        content_id, _content_card = self.create_content(title="终态")
        cancelled = self.transition(
            content_id, "--to", "cancelled", "--note", "选题不再做", actor="gm"
        )
        self.assertEqual(0, cancelled.returncode, cancelled.stderr)

        restarted = self.transition(content_id, "--to", "drafting", actor="content")

        self.assertEqual(1, restarted.returncode)
        self.assertIn("cancelled", restarted.stderr)

    def test_validate_requires_cancellation_metadata_for_cancelled_content(self):
        content_id, content_card = self.create_content(title="缺取消记录")
        record, _ = parse_frontmatter(content_card)
        record["status"] = "cancelled"
        record["events"].append(
            {
                "action": "cancel",
                "at": "2026-11-21T10:00:00+08:00",
                "actor": "gm",
                "from_status": "proposed",
                "to_status": "cancelled",
                "note": "选题不再做",
            }
        )
        write_frontmatter(content_card, record)

        result = self.run_workflow("validate")

        self.assertEqual(1, result.returncode)
        self.assertIn("cancellation", result.stderr)

    def test_review_and_close_refresh_views_without_touching_metrics(self):
        publication_id, publication_card = self.create_published_publication()
        record, _ = parse_frontmatter(publication_card)
        content_id = record["content_id"]
        metrics_path = (
            self.instance
            / "knowledge"
            / "content"
            / content_id
            / "publications"
            / publication_id
            / "指标.md"
        )
        self.metric_catalog()
        recorded = self.record_metrics(publication_id, "48h", {"views": 1234})
        self.assertEqual(0, recorded.returncode, recorded.stderr)
        history = metrics_path.read_bytes()

        reviewed = self.transition(
            publication_id,
            "--to",
            "reviewed",
            "--conclusion",
            "continue",
            "--next-action",
            "扩量",
            actor="growth",
        )
        self.assertEqual(0, reviewed.returncode, reviewed.stderr)
        closed = self.transition(content_id, "--to", "closed", actor="gm")
        self.assertEqual(0, closed.returncode, closed.stderr)

        built = self.run_workflow("build")
        self.assertEqual(0, built.returncode, built.stderr)
        self.assertEqual(history, metrics_path.read_bytes())

        calendar = (
            self.instance / "knowledge" / "business" / "选题日历.md"
        ).read_text(encoding="utf-8")
        self.assertNotIn(content_id, calendar)
        dashboard = json.loads(
            (self.instance / "knowledge" / "business" / "dashboard.json").read_text(
                encoding="utf-8"
            )
        )
        statuses = {entry["content_id"]: entry["status"] for entry in dashboard["contents"]}
        self.assertEqual("closed", statuses[content_id])
        channel_record = (
            self.instance / "knowledge" / "business" / "wechat" / "发布记录.md"
        ).read_text(encoding="utf-8")
        self.assertIn("reviewed", channel_record)
        self.assertIn("views=1234", channel_record)
        self.assertIn("continue", channel_record)
        self.assertIn("扩量", channel_record)

    # ---------- build ----------

    def test_build_writes_a_meaningful_generated_calendar_for_empty_instance(self):
        result = self.run_workflow("build")

        self.assertEqual(0, result.returncode, result.stderr)
        calendar = self.instance / "knowledge" / "business" / "选题日历.md"
        text = calendar.read_text(encoding="utf-8")
        self.assertIn("GENERATED FILE — READ ONLY", text)
        self.assertIn("tools/opc-workflow build", text)
        self.assertIn("knowledge/content/*/内容卡.md", text)
        self.assertIn("## 待排期选题", text)
        self.assertIn("当前没有待排期的内容。", text)
        self.assertIn("## 已排期内容", text)
        self.assertIn("当前没有已排期的内容。", text)
        self.assertIn("已生成选题日历：0 条待排期内容、0 条已排期内容", result.stdout)

    def test_calendar_splits_unscheduled_and_scheduled_contents(self):
        undated_id = "content-20261105-120000000000-a1b2c3d4"
        dated_id = "content-20261106-120000000000-b2c3d4e5"
        undated = self.valid_record(undated_id)
        dated = self.valid_record(dated_id)
        dated["target_date"] = "2026-12-01"
        dated["title"] = "已排期的选题"
        self.write_card(undated_id, undated)
        self.write_card(dated_id, dated)

        result = self.run_workflow("build")

        self.assertEqual(0, result.returncode, result.stderr)
        text = (self.instance / "knowledge" / "business" / "选题日历.md").read_text(
            encoding="utf-8"
        )
        unscheduled, scheduled = text.split("## 已排期内容")
        self.assertIn(undated_id, unscheduled)
        self.assertNotIn(dated_id, unscheduled)
        self.assertIn(dated_id, scheduled)
        self.assertIn("2026-12-01", scheduled)
        self.assertIn("已生成选题日历：1 条待排期内容、1 条已排期内容", result.stdout)

    def test_build_sorts_records_and_escapes_markdown_table_cells(self):
        later_id = "content-20261105-120000000001-b1b2c3d4"
        earlier_id = "content-20261105-120000000000-a1b2c3d4"
        later = self.valid_record(later_id)
        later["title"] = "后写的选题"
        later["created_at"] = "2026-11-05T12:00:01+00:00"
        later["events"][0]["at"] = later["created_at"]
        earlier = self.valid_record(earlier_id)
        earlier["title"] = "标题 | A\n下一行"
        earlier["source"] = "访谈 | 现场"
        earlier["summary"] = "第一行\n第二行"
        self.write_card(later_id, later)
        self.write_card(earlier_id, earlier)

        result = self.run_workflow("build")

        self.assertEqual(0, result.returncode, result.stderr)
        text = (self.instance / "knowledge" / "business" / "选题日历.md").read_text(
            encoding="utf-8"
        )
        self.assertLess(text.index(earlier_id), text.index(later_id))
        self.assertIn("标题 \\| A<br>下一行", text)
        self.assertIn("访谈 \\| 现场", text)
        self.assertIn("第一行<br>第二行", text)
        self.assertIn(f"[打开](../content/{earlier_id}/内容卡.md)", text)
        self.assertIn("| 内容 ID | 标题 | 目标日期 | 来源 | 摘要 | 状态 | 内容卡 |", text)

    def test_build_generates_channel_publication_record_without_copying_bodies(self):
        content_id, _content_card = self.create_ready_content(title="新增渠道发布")
        publication_id, publication_card = self.create_publication(content_id)
        draft = self.publication_draft(publication_id)
        secret_body = "绝不能复制到发布记录的渠道正文"
        draft.write_text(f"# 渠道稿\n\n{secret_body}\n", encoding="utf-8")
        reviewing = self.transition(
            publication_id,
            "--to",
            "reviewing",
            actor="content",
        )
        self.assertEqual(0, reviewing.returncode, reviewing.stderr)
        approved = self.transition(
            publication_id,
            "--decision",
            "approved",
            "--note",
            "不应复制的审批说明",
            actor="gm",
        )
        self.assertEqual(0, approved.returncode, approved.stderr)

        result = self.run_workflow("build")

        self.assertEqual(0, result.returncode, result.stderr)
        publication_view = (
            self.instance
            / "knowledge"
            / "business"
            / "wechat"
            / "发布记录.md"
        )
        text = publication_view.read_text(encoding="utf-8")
        self.assertIn("GENERATED FILE — READ ONLY", text)
        self.assertIn(publication_id, text)
        self.assertIn(content_id, text)
        self.assertIn("新增渠道发布", text)
        self.assertIn("reviewing", text)
        self.assertIn(
            f"../../content/{content_id}/publications/{publication_id}/发布卡.md",
            text,
        )
        self.assertIn(
            f"../../content/{content_id}/publications/{publication_id}/渠道稿.md",
            text,
        )
        self.assertNotIn(secret_body, text)
        self.assertNotIn("不应复制的审批说明", text)
        self.assertNotIn("artifact_hash", text)
        self.assertTrue(publication_card.is_file())

    def test_build_refuses_to_overwrite_manual_channel_record(self):
        content_id, _content_card = self.create_ready_content()
        self.create_publication(content_id)
        channel_dir = self.instance / "knowledge" / "business" / "wechat"
        channel_dir.mkdir()
        publication_view = channel_dir / "发布记录.md"
        legacy = "# 人工维护的发布记录\n".encode()
        publication_view.write_bytes(legacy)

        result = self.run_workflow("build")

        self.assertEqual(1, result.returncode)
        self.assertIn("不是生成文件", result.stderr)
        self.assertEqual(legacy, publication_view.read_bytes())
        self.assertFalse(
            (self.instance / "knowledge" / "business" / "选题日历.md").exists(),
            "任一生成目标冲突时不得部分更新其他视图",
        )

    def test_build_reflects_current_status_and_target_date_without_copying_draft(self):
        content_id, _card = self.create_content(
            title="有排期的主稿",
            target_date="2026-11-20",
        )
        self.assertEqual(
            0,
            self.transition(content_id, "--to", "drafting", actor="content").returncode,
        )
        self.main_draft(content_id).write_text(
            "# 不能复制进日历的正文\n\n这是稿件正文。\n",
            encoding="utf-8",
        )

        result = self.run_workflow("build")

        self.assertEqual(0, result.returncode, result.stderr)
        text = (self.instance / "knowledge" / "business" / "选题日历.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("2026-11-20", text)
        self.assertIn("drafting", text)
        self.assertNotIn("这是稿件正文", text)

    def test_build_preserves_previous_calendar_and_removes_temp_on_validation_failure(self):
        calendar = self.instance / "knowledge" / "business" / "选题日历.md"
        previous = "# 上一次有效日历\n\n不得被部分覆盖。\n"
        calendar.write_text(previous, encoding="utf-8")
        content_id = "content-20261105-120000000000-a1b2c3d4"
        self.write_card(content_id, raw_frontmatter="not-json")

        result = self.run_workflow("build")

        self.assertEqual(1, result.returncode)
        self.assertIn(f"knowledge/content/{content_id}/内容卡.md", result.stderr)
        self.assertEqual(previous, calendar.read_text(encoding="utf-8"))
        leftovers = [
            path.name
            for path in calendar.parent.iterdir()
            if path.name.startswith(".opc-workflow-calendar-")
        ]
        self.assertEqual([], leftovers)

    def test_build_refuses_to_overwrite_a_calendar_that_is_not_generated(self):
        # 手维护的旧日历不是生成物：build 不得静默覆盖掉它
        calendar = self.instance / "knowledge" / "business" / "选题日历.md"
        previous = "# 选题日历\n\n| 写稿日 | 选题 |\n|---|---|\n| 2026-11-05 | 旧选题 |\n"
        calendar.write_text(previous, encoding="utf-8")

        result = self.run_workflow("build")

        self.assertEqual(1, result.returncode)
        self.assertIn("拒绝覆盖", result.stderr)
        self.assertEqual(previous, calendar.read_text(encoding="utf-8"))

    def test_build_overwrites_a_calendar_it_generated_before(self):
        first = self.run_workflow("build")
        self.assertEqual(0, first.returncode, first.stderr)
        calendar = self.instance / "knowledge" / "business" / "选题日历.md"
        generated = calendar.read_text(encoding="utf-8")

        content_id = "content-20261105-120000000000-a1b2c3d4"
        self.write_card(content_id, self.valid_record(content_id))
        second = self.run_workflow("build")

        self.assertEqual(0, second.returncode, second.stderr)
        text = calendar.read_text(encoding="utf-8")
        self.assertNotEqual(generated, text)
        self.assertIn(content_id, text)

    def test_build_keeps_the_previous_calendar_when_writing_fails(self):
        # 目标位置被目录占住：原子替换会失败，旧内容原样保留
        calendar = self.instance / "knowledge" / "business" / "选题日历.md"
        calendar.mkdir()
        (calendar / "占位.md").write_text("旧内容\n", encoding="utf-8")

        result = self.run_workflow("build")

        self.assertEqual(1, result.returncode)
        self.assertTrue(calendar.is_dir())
        self.assertEqual("旧内容\n", (calendar / "占位.md").read_text(encoding="utf-8"))
        leftovers = [
            path.name
            for path in calendar.parent.iterdir()
            if path.name.startswith(".opc-workflow-calendar-")
        ]
        self.assertEqual([], leftovers)


if __name__ == "__main__":
    unittest.main()
