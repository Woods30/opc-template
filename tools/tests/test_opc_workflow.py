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
                        {"name": "disabled", "enabled": False},
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

    # ---------- transition / approval ----------

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
        self.assertIn("当前没有待排期的 proposed 内容。", text)
        self.assertIn("已生成选题日历：0 条待排期内容", result.stdout)

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
