import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from bugfix_automation.domain.capability_system import capability_status, render_capability_contract, resolve_capability_provider
from bugfix_automation.config import CanonicalFieldMapping, CapabilityProviderConfig, CapabilitySystemConfig, Config, FilterRule
from bugfix_automation.domain.filtering import filter_bugs, make_branch_name
from bugfix_automation.domain.prompt import render_codex_prompt
from bugfix_automation.reporting.reporter import conflict_index, write_reports
from bugfix_automation.domain.ai_cli import ai_cli_print_command
from bugfix_automation.orchestration.bug_runner import ai_cli_command, assert_scope_clean, codex_log_path
from bugfix_automation.git.worktree import out_of_scope_paths


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

    def test_make_branch_name_honors_empty_summary_fields(self) -> None:
        rows = [{
            "_excel_row": "46",
            "编号": "BUG-1",
            "提出人状态": "待处理",
            "来源系统": "小亦PC",
            "负责人": "谢浩杰",
            "状态": "处理中",
            "问题描述": "旧配置字段不该使用",
            "标题": "上传反馈不明显",
            "详情": "点击后没有进度",
        }]
        bug = filter_bugs(
            rows,
            assignee="",
            rules=(FilterRule("负责人", "equals", "谢浩杰", ("谢浩杰",)),),
            mapping=CanonicalFieldMapping(
                issue_id="编号",
                description="标题",
                remark="详情",
                assignee="负责人",
                assignee_status="状态",
            ),
        )[0]

        self.assertEqual(make_branch_name(bug, (), "202605120930"), "fix/bug-BUG-1-上传反馈不明显-202605120930")

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
            capability_contract="Capability system: Codex + Superpowers",
        )

        self.assertIn("apps/pc-web", prompt)
        self.assertIn("能力系统", prompt)
        self.assertIn("Capability system: Codex + Superpowers", prompt)
        self.assertIn("不要修改后端", prompt)
        self.assertIn("不要 push", prompt)
        self.assertIn("不要自动 git commit", prompt)
        self.assertIn("不要使用破坏性 git 命令", prompt)
        self.assertIn("lint/build/test", prompt)
        self.assertNotIn("bug-triage-agent", prompt)
        self.assertNotIn("frontend-fix-agent", prompt)
        self.assertNotIn("verification-agent", prompt)
        self.assertNotIn("branch-commit-agent", prompt)
        self.assertIn("一级分类: 个人空间", prompt)
        self.assertIn("二级分类: 文件上传交互", prompt)
        self.assertIn("备注: 页面反馈不明显", prompt)
        self.assertIn("补充初始化提示词", prompt)
        self.assertIn("apps/pc-web/src/app", prompt)
        self.assertIn("工作区: PC Web", prompt)

    def test_prompt_uses_capability_contract_instead_of_local_agent_workflow(self) -> None:
        bug = filter_bugs([
            {
                "_excel_row": "2",
                "序号": "87",
                "提出人状态": "处理中",
                "来源系统": "小亦PC",
                "对接人": "谢浩杰",
                "对接人状态": "",
                "问题描述": "账号离线状态",
            }
        ], assignee="谢浩杰")[0]

        prompt = render_codex_prompt(
            bug,
            target_app_path="apps/pc-web",
            capability_contract="Capability system: Claude Code + everything-claude-code\nUse ECC.",
            ai_tool_label="Claude Code",
        )

        self.assertIn("Capability system: Claude Code + everything-claude-code\nUse ECC.", prompt)
        self.assertIn("问题描述: 账号离线状态", prompt)
        self.assertIn("不要 push", prompt)
        self.assertNotIn("先委派 bug-triage-agent", prompt)
        self.assertNotIn("再委派 frontend-fix-agent", prompt)

    def test_prompt_can_name_claude_instead_of_codex(self) -> None:
        bug = filter_bugs([
            {
                "_excel_row": "2",
                "序号": "87",
                "提出人状态": "处理中",
                "来源系统": "小亦PC",
                "对接人": "谢浩杰",
                "对接人状态": "",
                "问题描述": "账号离线状态",
            }
        ], assignee="谢浩杰")[0]

        prompt = render_codex_prompt(bug, target_app_path="apps/pc-web", ai_tool_label="Claude Code")

        self.assertIn("Claude Code", prompt)
        self.assertNotIn("本地自动化流程启动的 Codex", prompt)
        self.assertNotIn("随本次 Codex 调用", prompt)

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
        selected_section = prompt.split("原始 Excel 行完整信息：", 1)[0]

        self.assertIn("问题描述: 账号离线状态", selected_section)
        self.assertNotIn("备注: 页面反馈不明显", selected_section)

    def test_prompt_honors_empty_selected_excel_fields(self) -> None:
        bug = filter_bugs([
            {
                "_excel_row": "2",
                "序号": "87",
                "提出人状态": "处理中",
                "来源系统": "小亦PC",
                "对接人": "谢浩杰",
                "对接人状态": "",
                "问题描述": "账号离线状态",
                "备注": "页面反馈不明显",
            }
        ], assignee="谢浩杰")[0]

        prompt = render_codex_prompt(bug, target_app_path="apps/pc-web", prompt_fields=())
        selected_section = prompt.split("原始 Excel 行完整信息：", 1)[0]

        self.assertIn("- 无", selected_section)
        self.assertNotIn("问题描述: 账号离线状态", selected_section)
        self.assertNotIn("备注: 页面反馈不明显", selected_section)

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
        selected_section = prompt.split("原始 Excel 行完整信息：", 1)[0]

        self.assertIn("提出日期: 2026/4/21", selected_section)
        self.assertIn("提出日期: 46133", prompt)

    def test_filter_bugs_uses_custom_canonical_mapping(self) -> None:
        rows = [{
            "_excel_row": "9",
            "编号": "BUG-9",
            "标题": "上传按钮无反馈",
            "详情": "点击上传后没有进度",
            "负责人": "谢浩杰",
            "状态": "处理中",
        }]

        bugs = filter_bugs(
            rows,
            assignee="",
            rules=(FilterRule("负责人", "equals", "谢浩杰", ("谢浩杰",)),),
            mapping=CanonicalFieldMapping(
                issue_id="编号",
                description="标题",
                remark="详情",
                assignee="负责人",
                assignee_status="状态",
            ),
        )

        self.assertEqual(bugs[0].issue_id, "BUG-9")
        self.assertEqual(bugs[0].description, "上传按钮无反馈")
        self.assertEqual(bugs[0].remark, "点击上传后没有进度")
        self.assertEqual(bugs[0].assignee, "谢浩杰")

    def test_prompt_includes_raw_excel_row_section(self) -> None:
        bug = filter_bugs([
            {
                "_excel_row": "2",
                "序号": "87",
                "提出人状态": "处理中",
                "来源系统": "小亦PC",
                "对接人": "谢浩杰",
                "问题描述": "账号离线状态",
                "自定义字段": "只有原始行里有",
            }
        ], assignee="谢浩杰")[0]

        prompt = render_codex_prompt(bug, target_app_path="apps/pc-web", prompt_fields=("问题描述",))

        self.assertIn("原始 Excel 行完整信息", prompt)
        self.assertIn("自定义字段: 只有原始行里有", prompt)

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

    def test_ai_cli_command_uses_codex_exec_mode(self) -> None:
        command = ai_cli_command("/usr/local/bin/codex", "/tmp/worktree", "prompt")

        self.assertEqual(command[:2], ["/usr/local/bin/codex", "exec"])
        self.assertIn("--cd", command)
        self.assertNotIn("--ask-for-approval", command)
        self.assertEqual(command[-1], "-")

    def test_ai_cli_command_uses_claude_print_mode(self) -> None:
        command = ai_cli_command("/usr/local/bin/claude", "/tmp/worktree", "prompt")

        self.assertEqual(command[:2], ["/usr/local/bin/claude", "--print"])
        self.assertIn("--permission-mode", command)
        self.assertIn("bypassPermissions", command)
        self.assertNotIn("exec", command)
        self.assertNotIn("--cd", command)

    def test_ai_cli_command_allows_claude_to_read_image_directories(self) -> None:
        command = ai_cli_command(
            "claude",
            "/tmp/worktree",
            "prompt",
            [Path("/tmp/bug-images/one.png"), Path("/tmp/bug-images/two.jpg")],
        )

        self.assertIn("--add-dir", command)
        self.assertIn("/tmp/bug-images", command)
        self.assertNotIn("--image", command)

    def test_ai_cli_print_command_uses_provider_specific_non_interactive_mode(self) -> None:
        self.assertEqual(ai_cli_print_command("claude"), ["claude", "--print"])
        self.assertEqual(ai_cli_print_command("codex"), ["codex", "exec", "-"])

    def test_capability_provider_auto_follows_cli_tool(self) -> None:
        base = Config(
            excel_path=Path("/tmp/bugs.xlsx"),
            sheet_name="Sheet1",
            assignee="谢浩杰",
            target_repo=Path("/tmp/repo"),
            target_app_path="apps/pc-web",
            worktree_root=Path("/tmp/worktrees"),
            runs_root=Path("/tmp/runs"),
            logs_root=Path("/tmp/logs"),
            launchd_label="local.test",
            cli_tool="claude",
            schedule_hour=22,
            schedule_minute=0,
            approval_web_port=8765,
            approval_api_port=8766,
        )

        self.assertEqual(resolve_capability_provider(base), "claude")
        self.assertEqual(resolve_capability_provider(replace(base, cli_tool="codex")), "codex")

    def test_capability_provider_explicit_config_wins(self) -> None:
        config = Config(
            excel_path=Path("/tmp/bugs.xlsx"),
            sheet_name="Sheet1",
            assignee="谢浩杰",
            target_repo=Path("/tmp/repo"),
            target_app_path="apps/pc-web",
            worktree_root=Path("/tmp/worktrees"),
            runs_root=Path("/tmp/runs"),
            logs_root=Path("/tmp/logs"),
            launchd_label="local.test",
            cli_tool="codex",
            schedule_hour=22,
            schedule_minute=0,
            approval_web_port=8765,
            approval_api_port=8766,
            capability_system=CapabilitySystemConfig(provider="claude"),
        )

        self.assertEqual(resolve_capability_provider(config), "claude")

    def test_claude_capability_status_reports_missing_required_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "ecc"
            (source / "agents").mkdir(parents=True)
            (source / "agents" / "planner.md").write_text("---\nname: planner\n---\n", encoding="utf-8")
            config = Config(
                excel_path=Path("/tmp/bugs.xlsx"),
                sheet_name="Sheet1",
                assignee="谢浩杰",
                target_repo=Path("/tmp/repo"),
                target_app_path="apps/pc-web",
                worktree_root=Path("/tmp/worktrees"),
                runs_root=Path("/tmp/runs"),
                logs_root=Path("/tmp/logs"),
                launchd_label="local.test",
                cli_tool="claude",
                schedule_hour=22,
                schedule_minute=0,
                approval_web_port=8765,
                approval_api_port=8766,
                capability_system=CapabilitySystemConfig(
                    claude=CapabilityProviderConfig(
                        source=str(source),
                        required_agents=("planner", "code-reviewer"),
                        required_skills=("tdd-workflow",),
                    )
                ),
            )

            status = capability_status(config)

        self.assertEqual(status["provider"], "claude")
        self.assertTrue(status["required"]["agents"][0]["available"])
        self.assertIn("Missing required Claude agent: code-reviewer", status["warnings"])
        self.assertIn("Missing required Claude skill: tdd-workflow", status["warnings"])

    def test_capability_contract_mentions_provider_native_capabilities(self) -> None:
        codex_config = Config(
            excel_path=Path("/tmp/bugs.xlsx"),
            sheet_name="Sheet1",
            assignee="谢浩杰",
            target_repo=Path("/tmp/repo"),
            target_app_path="apps/pc-web",
            worktree_root=Path("/tmp/worktrees"),
            runs_root=Path("/tmp/runs"),
            logs_root=Path("/tmp/logs"),
            launchd_label="local.test",
            cli_tool="codex",
            schedule_hour=22,
            schedule_minute=0,
            approval_web_port=8765,
            approval_api_port=8766,
            capability_system=CapabilitySystemConfig(
                codex=CapabilityProviderConfig(
                    source="superpowers",
                    required_skills=("superpowers:test-driven-development",),
                )
            ),
        )
        claude_config = replace(
            codex_config,
            cli_tool="claude",
            capability_system=CapabilitySystemConfig(
                claude=CapabilityProviderConfig(
                    source="/tmp/ecc",
                    required_agents=("planner", "code-reviewer"),
                    required_skills=("tdd-workflow",),
                )
            ),
        )

        codex_contract = render_capability_contract(codex_config)
        claude_contract = render_capability_contract(claude_config)
        self.assertIn("Codex + Superpowers", codex_contract)
        self.assertIn("superpowers:test-driven-development", codex_contract)
        self.assertIn("Claude Code + everything-claude-code", claude_contract)
        self.assertIn("planner, code-reviewer", claude_contract)
        self.assertIn("tdd-workflow", claude_contract)

    def test_log_path_uses_configured_cli_directory(self) -> None:
        config = Config(
            excel_path=Path("/tmp/bugs.xlsx"),
            sheet_name="Sheet1",
            assignee="谢浩杰",
            target_repo=Path("/tmp/repo"),
            target_app_path="apps/pc-web",
            worktree_root=Path("/tmp/worktrees"),
            runs_root=Path("/tmp/runs"),
            logs_root=Path("/tmp/logs"),
            launchd_label="local.test",
            cli_tool="claude",
            schedule_hour=22,
            schedule_minute=0,
            approval_web_port=8765,
            approval_api_port=8766,
        )

        self.assertEqual(codex_log_path(config, "fix/bug-1-demo"), Path("/tmp/logs/claude/fix-bug-1-demo.log"))


if __name__ == "__main__":
    unittest.main()
