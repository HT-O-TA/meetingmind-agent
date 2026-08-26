"""生成冻结的、项目自编合成待办抽取数据集并执行隐私/泄漏检查。"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

try:
    from .common import SCHEMA_VERSION, sha256_file, validate_todos
except ImportError:  # 允许直接执行脚本。
    from common import SCHEMA_VERSION, sha256_file, validate_todos


ACTION_POOLS = {
    "train": [
        "整理发布清单", "更新接口文档", "核对采购报价", "提交测试报告", "完成数据备份",
        "安排客户回访", "修复登录缺陷", "准备演示材料", "汇总风险列表", "检查监控告警",
        "更新项目排期", "完成权限审计", "整理会议纪要", "验证恢复脚本", "编写上线公告",
        "清理无效账号", "统计使用反馈", "准备培训课件", "对齐验收标准", "复核合同条款",
        "提交容量计划", "完成代码评审", "整理竞品分析", "更新值班表", "确认机房资源",
        "补充接口用例", "建立回滚预案", "汇总客服工单", "准备预算说明", "复查数据口径",
        "更新依赖清单", "完成安全扫描", "整理故障时间线", "提交设计草图", "核验库存数量",
        "准备周会材料",
    ],
    "validation": [
        "整理迁移步骤", "确认法务意见", "补充压测脚本", "更新用户手册",
        "核对发票明细", "准备复盘提纲", "检查备机状态", "提交采购申请",
    ],
    "test": [
        "整理客户问题清单", "完成回滚演练", "更新灾备手册", "核对交付范围",
        "准备招标材料", "补充数据字典", "检查证书期限", "提交会议室预订",
        "汇总试用反馈", "验证告警规则",
    ],
}

NEGATIVE_POOLS = {
    "train": [
        "可以考虑改版首页，但今天不做决定。", "要不要增加夜间值班？", "登录缺陷已经修复完毕。",
        "原定的数据迁移任务已经取消。", "大家讨论了采购预算，没有分配工作。", "也许以后可以增加培训。",
        "监控方案还在比较，暂不执行。", "上周的客户回访已经完成。", "是否需要更新接口文档？",
        "这只是一个设想，不形成行动项。", "会议回顾了去年的项目结果。", "负责人和计划均未确定。",
    ],
    "validation": [
        "新的办公地点还在讨论。", "安全扫描昨天已经完成。", "要不要调整交付日期？", "候选方案全部暂缓。",
    ],
    "test": [
        "可以考虑更换供应商，目前不立项。", "权限审计已经在上午完成。", "是否需要增加培训场次？", "原定的机房巡检已经取消。",
    ],
}

ASSIGNEES = ["成员甲", "成员乙", "成员丙", "成员丁"]
DEADLINES = ["周一前", "周二下班前", "周三前", "本周四", "周五中午前", "下周一前", "发布前", "月底前"]
FORMS = (
    "请{assignee}在{deadline}{content}。",
    "{content}这项工作由{assignee}负责，期限是{deadline}。",
    "{assignee}确认会在{deadline}{content}。",
    "会议决定：{assignee}需要于{deadline}{content}。",
    "行动项是{content}，负责人{assignee}，截止到{deadline}。",
    "{assignee}，麻烦你{deadline}{content}。",
)


def format_timestamp(seconds: float) -> str:
    minutes = int(seconds // 60)
    remainder = seconds - minutes * 60
    return f"{minutes:02d}:{remainder:05.2f}"


def action_output(sample_id: str, content: str, assignee: str, deadline: str, speaker: str, timestamp: float, priority: str = "unknown") -> dict[str, Any]:
    uncertainties = []
    if not assignee:
        uncertainties.append("assignee_missing")
    if not deadline:
        uncertainties.append("deadline_missing")
    return {
        "content": content,
        "assignee": assignee,
        "deadline": deadline,
        "priority": priority,
        "source_id": sample_id,
        "source_type": "synthetic_meeting",
        "speaker": speaker,
        "timestamp": timestamp,
        "uncertainties": uncertainties,
        "degradation_info": [],
    }


def positive_record(split: str, index: int, content: str) -> dict[str, Any]:
    sample_id = f"syn-{split[:3]}-{index:03d}"
    speaker = ASSIGNEES[(index + 1) % len(ASSIGNEES)]
    assignee = ASSIGNEES[index % len(ASSIGNEES)]
    deadline = DEADLINES[index % len(DEADLINES)]
    timestamp = float(8 + index % 7 * 4)
    task_line = FORMS[index % len(FORMS)].format(assignee=assignee, deadline=deadline, content=content)
    if index % 11 == 9:
        task_line = f"{content}需要继续推进，{assignee}来负责。"
        deadline = ""
    elif index % 11 == 10:
        task_line = f"请在{deadline}{content}，具体负责人待定。"
        assignee = ""
    priority = "high" if index % 13 == 12 else "unknown"
    if priority == "high":
        task_line = f"高优先级：{task_line}"
    transcript = "\n".join(
        [
            "[00:00.00] 成员甲: 今天先确认当前进展。",
            f"[{format_timestamp(timestamp)}] {speaker}: {task_line}",
            f"[{format_timestamp(timestamp + 5)}] 成员丁: 收到，后续在周会上核对状态。",
        ]
    )
    return make_record(split, index, transcript, [action_output(sample_id, content, assignee, deadline, speaker, timestamp, priority)])


def negative_record(split: str, index: int, text: str) -> dict[str, Any]:
    sample_id = f"syn-{split[:3]}-{index:03d}"
    transcript = "\n".join(
        [
            "[00:00.00] 成员甲: 下面讨论备选方案。",
            f"[00:08.00] 成员乙: {text}",
            "[00:13.00] 成员丙: 明白，等信息明确后再决定。",
        ]
    )
    return make_record(split, index, transcript, [])


def make_record(split: str, index: int, transcript: str, expected: list[dict[str, Any]]) -> dict[str, Any]:
    sample_id = f"syn-{split[:3]}-{index:03d}"
    return {
        "schema_version": SCHEMA_VERSION,
        "sample_id": sample_id,
        "meeting_id": f"meeting-{sample_id}",
        "split": split,
        "language": "zh-CN",
        "source_kind": "project_authored_synthetic",
        "source_type": "synthetic_meeting",
        "annotation_method": "deterministic_template_ground_truth",
        "human_reviewed": False,
        "contains_real_user_data": False,
        "transcript": transcript,
        "expected": expected,
    }


def multi_action_records(start_index: int = 15) -> list[dict[str, Any]]:
    records = []
    cases = [
        ("制定切换检查表", "成员乙", "周四前", "准备故障通报模板", "成员丙", "发布前"),
        ("核对培训名单", "成员甲", "下周一前", "预订培训设备", "成员丁", "周五前"),
    ]
    for offset, (content_a, owner_a, deadline_a, content_b, owner_b, deadline_b) in enumerate(cases):
        index = start_index + offset
        sample_id = f"syn-tes-{index:03d}"
        transcript = "\n".join(
            [
                "[00:00.00] 成员甲: 最后确认两个行动项。",
                f"[00:09.00] 成员乙: {owner_a}在{deadline_a}{content_a}。",
                f"[00:17.00] 成员丙: {owner_b}负责在{deadline_b}{content_b}。",
                "[00:23.00] 成员甲: 以上两项下次会议检查。",
            ]
        )
        expected = [
            action_output(sample_id, content_a, owner_a, deadline_a, "成员乙", 9.0),
            action_output(sample_id, content_b, owner_b, deadline_b, "成员丙", 17.0),
        ]
        records.append(make_record("test", index, transcript, expected))
    return records


def build_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for split in ("train", "validation", "test"):
        index = 1
        for content in ACTION_POOLS[split]:
            records.append(positive_record(split, index, content))
            index += 1
        for text in NEGATIVE_POOLS[split]:
            records.append(negative_record(split, index, text))
            index += 1
    records.extend(multi_action_records())
    return records


def lint_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    errors: list[str] = []
    pii_patterns = {
        "email": re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}"),
        "mainland_phone": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
        "mainland_id": re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"),
    }
    seen_samples: set[str] = set()
    split_meetings: dict[str, set[str]] = {"train": set(), "validation": set(), "test": set()}
    for record in records:
        sample_id = record["sample_id"]
        if sample_id in seen_samples:
            errors.append(f"duplicate sample_id: {sample_id}")
        seen_samples.add(sample_id)
        split_meetings[record["split"]].add(record["meeting_id"])
        if record["contains_real_user_data"] or record["human_reviewed"]:
            errors.append(f"truthfulness flag mismatch: {sample_id}")
        for name, pattern in pii_patterns.items():
            if pattern.search(record["transcript"]):
                errors.append(f"{name} detected: {sample_id}")
        try:
            validated = validate_todos(record["expected"])
        except ValueError as exc:
            errors.append(f"schema invalid {sample_id}: {exc}")
            continue
        if validated != record["expected"]:
            errors.append(f"field order/value drift: {sample_id}")
        for item in validated:
            if item["source_id"] != sample_id or item["source_type"] != record["source_type"]:
                errors.append(f"source mismatch: {sample_id}")
            for field in ("content", "assignee", "deadline"):
                if item[field] and item[field] not in record["transcript"]:
                    errors.append(f"ungrounded {field}: {sample_id}")
    split_names = list(split_meetings)
    for left_index, left in enumerate(split_names):
        for right in split_names[left_index + 1 :]:
            overlap = split_meetings[left] & split_meetings[right]
            if overlap:
                errors.append(f"meeting leakage {left}/{right}: {sorted(overlap)}")
    return {
        "valid": not errors,
        "errors": errors,
        "counts": {split: sum(record["split"] == split for record in records) for split in split_meetings},
        "positive_counts": {
            split: sum(record["split"] == split and bool(record["expected"]) for record in records)
            for split in split_meetings
        },
        "real_user_record_count": sum(bool(record["contains_real_user_data"]) for record in records),
        "human_reviewed_record_count": sum(bool(record["human_reviewed"]) for record in records),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "data" / "meeting_todo_synthetic_v1.jsonl")
    parser.add_argument("--manifest", type=Path, default=Path(__file__).parent / "data" / "meeting_todo_synthetic_v1.manifest.json")
    args = parser.parse_args()
    records = build_records()
    lint = lint_records(records)
    if not lint["valid"]:
        raise SystemExit("dataset lint failed:\n" + "\n".join(lint["errors"]))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    try:
        dataset_display_path = args.output.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        dataset_display_path = args.output.name
    try:
        generator_display_path = Path(__file__).resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        generator_display_path = Path(__file__).name
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "dataset_path": dataset_display_path,
        "dataset_sha256": sha256_file(args.output),
        "generator_path": generator_display_path,
        "generator_sha256": sha256_file(__file__),
        **lint,
        "limitations": [
            "全部样本为项目自编合成文本，不包含真实会议或真实用户数据。",
            "标签由确定性模板生成且未经人工复核，只能验证训练工程闭环。",
            "测试集按 meeting_id 隔离，但与训练集共享语言模板，不能代表真实领域泛化。",
        ],
    }
    args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
