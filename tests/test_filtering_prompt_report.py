import json
import tempfile
import unittest
from pathlib import Path

from bugfix_automation.config import FilterRule
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
            {"_excel_row": "8", "序号": "93", "提出人状态": "处理中", "来源系统": "小亦PC", "对接人": "谢浩杰", "对接人状态": "已处理", "问题描述": "可配置关闭状态"},
        ]

        bugs = filter_bugs(rows, assignee="谢浩杰", excluded_assignee_statuses={"已处理"})

        self.assertEqual([bug.issue_id for bug in bugs], ["87", "88"])
        self.assertEqual(bugs[0].excel_row, 2)
        self.assertEqual(bugs[1].source_system, "小亦APP")

    def test_filter_bugs_supports_custom_field_rules(self) -> None:
        rows = [
            {"_excel_row": "2", "序号": "1", "负责人": "谢浩杰", "端": "PC", "状态": "处理中", "问题描述": "保留"},
            {"_excel_row": "3", "序号": "2", "负责人": "谢浩杰", "端": "后端", "状态": "处理中", "问题描述": "跳过"},
            {"_excel_row": "4", "序号": "3", "负责人": "谢浩杰", "端": "PC", "状态": "已处理", "问题描述": "跳过"},
        ]

        bugs = filter_bugs(
            rows,
            assignee="",
            rules=(
                FilterRule("负责人", "equals", "谢浩杰", ("谢浩杰",)),
                FilterRule("端", "in", values=("PC", "APP")),
                FilterRule("状态", "not_in", values=("已处理",)),
            ),
        )

        self.assertEqual([bug.issue_id for bug in bugs], ["1"])

    def test_filter_bugs_matches_multi_value_cells(self) -> None:
        rows = [
            {"_excel_row": "132", "序号": "37", "提出人状态": "待处理", "来源系统": "小亦APP,小亦PC", "对接人": "谢浩杰", "对接人状态": "处理中", "问题描述": "待办去重"},
            {"_excel_row": "133", "序号": "38", "提出人状态": "待处理", "来源系统": "小亦PC,小亦后台管理系统", "对接人": "谢浩杰", "对接人状态": "处理中", "问题描述": "混入后台跳过"},
            {"_excel_row": "134", "序号": "39", "提出人状态": "待处理", "来源系统": "小亦PC", "对接人": "谢浩杰、魏胤择", "对接人状态": "处理中", "问题描述": "多人对接跳过"},
        ]

        bugs = filter_bugs(
            rows,
            assignee="",
            rules=(
                FilterRule("对接人", "equals", "谢浩杰", ("谢浩杰",)),
                FilterRule("对接人状态", "not_in", values=("已解决", "已处理")),
                FilterRule("来源系统", "all_in", values=("小亦PC", "小亦APP")),
                FilterRule("提出人状态", "in", values=("待处理", "处理中")),
            ),
        )

        self.assertEqual([bug.issue_id for bug in bugs], ["37"])

    def test_make_branch_name_is_stable_and_local_fix_prefixed(self) -> None:
        rows = [{"_excel_row": "2", "序号": "87", "提出人状态": "处理中", "来源系统": "小亦PC", "对接人": "谢浩杰", "对接人状态": "", "问题描述": "账号离线状态异常 / app"}]
        bug = filter_bugs(rows, assignee="谢浩杰")[0]

        self.assertEqual(make_branch_name(bug, ("问题描述",), "202605120930"), "fix/bug-87-账号离线状态异常app-202605120930")

    def test_make_branch_name_uses_chinese_summary_for_current_bug(self) -> None:
        rows = [{"_excel_row": "46", "序号": "1", "提出人状态": "待处理", "来源系统": "小亦PC", "对接人": "谢浩杰", "对接人状态": "处理中", "问题描述": "在个人空间上传附件后，页面反馈不够明显，没有进度展示；另外页面为空状态时，把页面中间“暂无上传文件”上面的上传icon去掉"}]
        bug = filter_bugs(rows, assignee="谢浩杰")[0]

        self.assertEqual(make_branch_name(bug, ("问题描述",), "202605120930"), "fix/bug-1-个人空间上传附件页面反馈不够明显-202605120930")

    def test_make_branch_name_uses_configured_summary_fields(self) -> None:
        rows = [{
            "_excel_row": "46",
            "序号": "1",
            "提出人状态": "待处理",
            "来源系统": "小亦PC",
            "对接人": "谢浩杰",
            "对接人状态": "处理中",
            "一级分类": "个人空间",
            "问题描述": "上传反馈不明显",
        }]
        bug = filter_bugs(rows, assignee="谢浩杰")[0]

        self.assertEqual(make_branch_name(bug, ("一级分类", "问题描述"), "202605120930"), "fix/bug-1-个人空间上传反馈不明显-202605120930")

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

        prompt = render_codex_prompt(
            bug,
            target_app_path="apps/pc-web",
            prompt_fields=("一级分类", "二级分类", "问题描述", "备注"),
            prompt_template="补充初始化提示词",
            context_paths=("apps/pc-web/src/app",),
            workspace_name="PC Web",
        )

        self.assertIn("apps/pc-web", prompt)
        self.assertIn("不要修改后端", prompt)
        self.assertIn("不要 push", prompt)
        self.assertIn("bug-triage-agent", prompt)
        self.assertIn("frontend-fix-agent", prompt)
        self.assertIn("verification-agent", prompt)
        self.assertIn("branch-commit-agent", prompt)
        self.assertIn("不要自动 git commit", prompt)
        self.assertIn("一级分类: 个人空间", prompt)
        self.assertIn("二级分类: 文件上传交互", prompt)
        self.assertIn("备注: 页面反馈不明显", prompt)
        self.assertIn("补充初始化提示词", prompt)
        self.assertIn("apps/pc-web/src/app", prompt)
        self.assertIn("工作区: PC Web", prompt)

    def test_prompt_only_includes_selected_excel_fields(self) -> None:
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
            }
        ], assignee="谢浩杰")[0]

        prompt = render_codex_prompt(bug, target_app_path="apps/pc-web", prompt_fields=("问题描述",))

        self.assertIn("问题描述: 账号离线状态", prompt)
        self.assertNotIn("备注: 页面反馈不明显", prompt)

    def test_prompt_uses_formatted_known_field_values(self) -> None:
        bug = filter_bugs([
            {
                "_excel_row": "46",
                "序号": "1",
                "提出人状态": "待处理",
                "来源系统": "小亦PC",
                "对接人": "谢浩杰",
                "对接人状态": "处理中",
                "提出日期": "46133",
                "问题描述": "上传反馈",
            }
        ], assignee="谢浩杰")[0]

        prompt = render_codex_prompt(bug, target_app_path="apps/pc-web", prompt_fields=("提出日期",))

        self.assertIn("提出日期: 2026/4/21", prompt)
        self.assertNotIn("提出日期: 46133", prompt)

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
        self.assertIn("--cd", command)
        self.assertNotIn("--ask-for-approval", command)
        self.assertEqual(command[-1], "-")


if __name__ == "__main__":
    unittest.main()
