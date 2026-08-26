"""Jira Cloud 最小真实联调；默认只读，写入需要双重显式参数。"""
import argparse
import asyncio
import json

from app.agents.tools.enterprise_tools import JiraClient


def parse_args():
    parser = argparse.ArgumentParser(description="MeetingMind Jira Cloud smoke test")
    parser.add_argument("--issue-key", help="只读查询，例如 MM-1")
    parser.add_argument("--create-project", help="创建 Issue 的项目 Key，例如 MM")
    parser.add_argument("--summary", default="MeetingMind 阶段 2 真实联调")
    parser.add_argument(
        "--confirm-create",
        choices=["NO", "CREATE"],
        default="NO",
        help="必须明确传 CREATE 才会执行外部写",
    )
    return parser.parse_args()


async def main():
    args = parse_args()
    if not args.issue_key and not args.create_project:
        raise SystemExit("请提供 --issue-key 做只读验证，或提供 --create-project")
    if args.create_project and args.confirm_create != "CREATE":
        raise SystemExit("创建已阻止：请在确认 Jira 项目后显式传 --confirm-create CREATE")

    client = JiraClient()
    try:
        if args.issue_key:
            result = await client.get_issue(args.issue_key)
        else:
            result = await client.create_issue(
                args.create_project,
                "Task",
                args.summary,
                "由 MeetingMind 阶段 2 真实联调脚本创建。",
            )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
