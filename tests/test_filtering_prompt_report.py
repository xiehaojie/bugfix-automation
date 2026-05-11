import json
import tempfile
import unittest
from pathlib import Path

from bugfix_automation.filtering import filter_bugs, make_branch_name
from bugfix_automation.prompt import render_codex_prompt
from bugfix_automation.reporter import conflict_index, write_reports
from bugfix_automation.runner import assert_scope_clean, codex_command
from bugfix_automation.worktree import out_of_scope_paths


class FilteringPromptReportTest(unittest.TestCase):
    def test_filter_bugs_keeps_only_matching_frontend_rows(self) -> None:
        rows = [
            {"_excel_row": "2", "序号": "87", "提出人状态": "处理中", "来源系统": "小亦PC", "对接人": "谢浩杰", "对接人状态": "", "问题描述": "账号离线状态"},
            {"_excel_row": "3", "序号": "88", "提出人状态": "待处理", "来源系统": "小亦APP", "对接人": "谢浩杰", "对接人状态": "处理中", "问题描述": "按钮遮挡"},
            {"_excel_row": "4", "序号": "89", "提出人状态": "已解决", "来源系统": "小亦PC", "对接人": "谢浩杰", "对接人状态": "处理中", "问题描述": "跳过"},
            {"_excel_row": "5", "序号": "90", "提出人状态": "处理中", "来源系统": "后台", "对接人": "谢浩杰", "对接人状态": "处理中", "问题描述": "跳过"},
            {"_excel_row": "6", "序号": "91", "提出人状态": "处理中", "来源系统": "小亦PC", "对接人": "其他人", "对接人状态": "处理中", "问题描述": "跳过"},
            {"_excel_row": "7", "序号": "92", "提出人状态": "处理中", "来源系统": "小亦PC", "对接人": "谢浩杰", "对接人状态": "已解决", "问题描述": "跳过"},
        ]

        bugs = filter_bugs(rows, assignee="谢浩杰")

        self.assertEqual([bug.issue_id for bug in bugs], ["87", "88"])
        self.assertEqual(bugs[0].excel_row, 2)
        self.assertEqual(bugs[1].source_system, "小亦APP")

    def test_make_branch_name_is_stable_and_local_fix_prefixed(self) -> None:
        rows = [{"_excel_row": "2", "序号": "87", "提出人状态": "处理中", "来源系统": "小亦PC", "对接人": "谢浩杰", "对接人状态": "", "问题描述": "账号离线状态异常 / app"}]
        bug = filter_bugs(rows, assignee="谢浩杰")[0]

        self.assertEqual(make_branch_name(bug), "fix/87-账号离线状态异常app")

    def test_make_branch_name_uses_chinese_summary_for_current_bug(self) -> None:
        rows = [{"_excel_row": "46", "序号": "1", "提出人状态": "待处理", "来源系统": "小亦PC", "对接人": "谢浩杰", "对接人状态": "处理中", "问题描述": "在个人空间上传附件后，页面反馈不够明显，没有进度展示；另外页面为空状态时，把页面中间“暂无上传文件”上面的上传icon去掉"}]
        bug = filter_bugs(rows, assignee="谢浩杰")[0]

        self.assertEqual(make_branch_name(bug), "fix/1-个人空间上传附件页面反馈不够明显")

    def test_prompt_restricts_scope_and_remote_behavior(self) -> None:
        bug = filter_bugs([
            {
                "_excel_row": "2",
                "序号": "87",
                "提出人状态": "处理中",
                "来源系统": "小亦PC",
                "一级分类": "个人空间",
                "二级分类": "文件上传交互",
                "提出人": "齐震杰",
                "对接人": "谢浩杰",
                "对接人状态": "",
                "问题描述": "账号离线状态",
                "备注": "页面反馈不明显",
                "备注2": "需要参考截图",
            }
        ], assignee="谢浩杰")[0]

        prompt = render_codex_prompt(bug, target_app_path="apps/pc-web")

        self.assertIn("apps/pc-web", prompt)
        self.assertIn("不要修改后端", prompt)
        self.assertIn("不要 push", prompt)
        self.assertIn("bug-triage-agent", prompt)
        self.assertIn("frontend-fix-agent", prompt)
        self.assertIn("verification-agent", prompt)
        self.assertIn("branch-commit-agent", prompt)
        self.assertIn("一级分类: 个人空间", prompt)
        self.assertIn("二级分类: 文件上传交互", prompt)
        self.assertIn("备注: 页面反馈不明显", prompt)

    def test_filter_bugs_converts_excel_serial_dates_for_report_fields(self) -> None:
        bug = filter_bugs([
            {
                "_excel_row": "46",
                "序号": "1",
                "提出人状态": "待处理",
                "来源系统": "小亦PC",
                "对接人": "谢浩杰",
                "对接人状态": "处理中",
                "提出日期": "46133",
                "解决日期": "46134",
                "问题描述": "上传反馈",
            }
        ], assignee="谢浩杰")[0]

        self.assertEqual(bug.request_date, "2026/4/21")
        self.assertEqual(bug.resolved_date, "2026/4/22")

    def test_write_reports_creates_json_and_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            json_path, md_path, approval_path = write_reports(
                output,
                [
                    {
                        "issue_id": "87",
                        "excel_row": 2,
                        "status": "dry-run",
                        "branch": "fix/bug-87-demo",
                        "primary_category": "个人空间",
                        "secondary_category": "文件上传交互",
                        "requester": "齐震杰",
                        "description": "页面反馈不明显",
                        "remark": "去掉上传 icon",
                        "remark2": "参考截图",
                    }
                ],
            )

            data = json.loads(json_path.read_text(encoding="utf-8"))
            markdown = md_path.read_text(encoding="utf-8")
            approval = approval_path.read_text(encoding="utf-8")

        self.assertEqual(data["results"][0]["issue_id"], "87")
        self.assertIn("fix/bug-87-demo", markdown)
        self.assertIn("早上审批报告", approval)
        self.assertIn("一级分类: `个人空间`", approval)
        self.assertIn("二级分类: `文件上传交互`", approval)
        self.assertIn("问题描述: 页面反馈不明显", approval)
        self.assertIn("备注: 去掉上传 icon", approval)

    def test_conflict_index_detects_multiple_bugs_touching_same_file(self) -> None:
        conflicts = conflict_index([
            {"issue_id": "87", "status": "committed", "changed_files": ["apps/pc-web/src/a.tsx"]},
            {"issue_id": "88", "status": "committed", "changed_files": ["apps/pc-web/src/a.tsx", "apps/pc-web/src/b.tsx"]},
            {"issue_id": "89", "status": "failed", "changed_files": ["apps/pc-web/src/a.tsx"]},
        ])

        self.assertEqual(conflicts, {"apps/pc-web/src/a.tsx": ["87", "88"]})

    def test_out_of_scope_paths_rejects_backend_and_allows_agent_files(self) -> None:
        changed = [
            "apps/pc-web/src/app/page.tsx",
            ".codex/agents/frontend-fix-agent.toml",
            ".codex/",
            ".bugfix-automation-bin/",
            "apps/server/src/main.java",
        ]

        self.assertEqual(out_of_scope_paths(changed, "apps/pc-web"), ["apps/server/src/main.java"])

    def test_assert_scope_clean_raises_for_out_of_scope_paths(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "检测到超出前端范围的改动"):
            assert_scope_clean(["apps/pc-web/src/app/page.tsx", "packages/shared/index.ts"], "apps/pc-web")

    def test_codex_command_uses_workspace_sandbox_and_never_approval(self) -> None:
        command = codex_command("/usr/local/bin/codex", "/tmp/worktree", "prompt")

        self.assertEqual(command[:2], ["/usr/local/bin/codex", "exec"])
        self.assertIn("--sandbox", command)
        self.assertIn("workspace-write", command)
        self.assertNotIn("--ask-for-approval", command)
        self.assertIn("--cd", command)
        self.assertEqual(command[-1], "-")


if __name__ == "__main__":
    unittest.main()
