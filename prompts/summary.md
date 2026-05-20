请基于下面这次实际代码改动，生成一个适合 git 分支名和提交标题的中文摘要。

要求：
- 只输出摘要本身，不要解释。
- 不要包含 fix(scope)、序号、冒号、标点。
- 12 到 24 个中文字符左右。
- 摘要必须描述本次代码改动，而不是复述原始 bug。

Bug 序号: {issue_id}
原始问题: {description}

改动文件:
{changed_files}

Diff 统计:
{diff_stat}

Diff 片段:
{diff_sample}
