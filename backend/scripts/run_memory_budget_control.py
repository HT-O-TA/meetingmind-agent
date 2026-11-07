"""离线测量完整会话历史经过默认上下文组装预算后的变化。"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import subprocess
import sys
from collections import Counter
from pathlib import Path
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.core.config import Settings
from app.services import context_assembler, token_budget_ledger


DATASET = BACKEND / "evaluation/datasets/memory_budget_longsession_v1.jsonl"
BASELINE_REPORT = BACKEND / "evaluation/reports/memory_budget_longsession_v1.json"
REPORT = BASELINE_REPORT.with_name("memory_budget_longsession_v2.json")
# 在编写本脚本前完成事实标注并记录；不同输入不得覆盖同版本报告。
FROZEN_DATASET_SHA256 = "85e74b5508542d5107764d5e34033914bf6f1ba1173ee46bfd95f6ade0821835"

METHOD = [
    "会话按 user_id:session_id:conversation_id 隔离；短期记忆默认留最近10轮，线上按任务命名空间取最近3轮并按从新到旧传入组装器。",
    "本实验绕过线上记忆写入清洗、存储与读取窗口，把全部历史按记忆轮次格式渲染；每段只测最后一个问题，不计最后一轮回答。",
    "A 按时间顺序原样拼接所有历史轮次，无裁剪或组装标签；B 把相同轮次由新到旧传入 assemble_state 的 raw_context，并传入同一个最终问题。",
    "组装器先给任务锚点和包装预留字符，按来源权限排序，工具和检索证据优先于会话历史。历史条目以当前问题与条目单项预算内前缀共有的不重复汉字二元组和不区分大小写的拉丁字母/数字串数量排序，同分沿用原优先级及输入顺序。这样早期相关轮次也能竞争有限的席位，标注只用于事后计分。",
    "已有标准会话轮次标题的条目直接复用该标题，其余历史条目使用短来源标签，以减少重复包装。外部内容边界和清单中的来源、权限与引用字段保留。",
    "空项、重复项、超文档配额、超项数或剩余字符不够最小内容的条目记为 dropped，逐项给出 reason；保留但缩短的条目记 included.truncated。",
    "B 使用代码默认总字符、单项字符和项数预算；输入仅有会话历史，不含任务锚点、检索和工具证据，不执行 TokenBudgetLedger 的模型调用门禁。",
    "A/B 均附同一个最终问题，用 ModelTokenCounter.count_text 计数；默认 Qwen 模型按 ceil(1.5×中日韩统一表意文字基本区字符数 + 其余字符数/4) 近似，不含消息协议开销。",
    "事实保留按预标注文本是否逐字出现在历史上下文判定；损失按事实对应轮次的清单记录归因，不调用模型。",
]


def measure(session, assembler, counter, model):
    turns = session["turns"]
    blocks = [f"【会话轮次】\n问: {turn['question']}\n答: {turn['answer']}" for turn in turns]
    baseline = "\n\n".join(blocks)
    question = session["final_question"]
    assembly = assembler.assemble_state(
        {"raw_context": blocks[::-1], "question": question}, consumer="memory_budget_control"
    )
    baseline_count = counter.count_text(f"{baseline}\n\n问: {question}", model)
    clipped_count = counter.count_text(f"{assembly.text}\n\n问: {question}", model)

    def turn_number(item):
        # content_ref 从最新轮（索引 0）开始，标注按会话时间从第 1 轮开始。
        return len(turns) - int(item["content_ref"].rsplit(":", 1)[1])

    included = {turn_number(item): item for item in assembly.manifest["included"]}
    dropped = {turn_number(item): item["reason"] for item in assembly.manifest["dropped"]}
    truncated = [
        {
            "turn": turn,
            "original_chars": item["original_chars"],
            "included_chars": item["included_chars"],
        }
        for turn, item in included.items()
        if item["truncated"]
    ]
    # 无截断时可直接重拼 B 的保留轮次，量化真实 B 多出的包装与来源标签。
    retained_only_tokens = None
    if not truncated:
        retained_text = "\n\n".join(blocks[turn - 1] for turn in included)
        retained_only_tokens = counter.count_text(f"{retained_text}\n\n问: {question}", model).tokens
    facts = []
    for fact in session["key_facts"]:
        phrase, turn = fact["text"], fact["turn"]
        in_a = phrase in baseline
        in_b = phrase in assembly.text
        if not in_a or phrase in question or phrase not in blocks[turn - 1]:
            raise ValueError(f"事实标注或最终问题有误：{session['session_id']} 第 {turn} 轮")
        reason = None
        if not in_b:
            if turn in dropped:
                reason = dropped[turn]
            elif included[turn]["truncated"]:
                reason = "truncated"
            else:
                raise ValueError(f"无法从清单解释事实损失：{session['session_id']} 第 {turn} 轮")
        facts.append({
            **fact,
            "citation_ids": turns[turn - 1]["citation_ids"],
            "present_in_a": in_a,
            "present_in_b": in_b,
            "loss_reason": reason,
        })

    kept = sum(fact["present_in_b"] for fact in facts)
    return {
        "session_id": session["session_id"],
        "meeting_id": session["meeting_id"],
        "topic": session["topic"],
        "turn_count_including_final_question": len(turns) + 1,
        "history_turn_count": len(turns),
        "baseline_a": {
            "input_tokens": baseline_count.tokens,
            "history_context_chars": len(baseline),
            "kept_items": len(turns),
            "dropped_count": 0,
            "truncated_count": 0,
            "retained_key_facts": len(facts),
            "key_fact_retention_rate": 1.0,
        },
        "assembled_b": {
            "input_tokens": clipped_count.tokens,
            "retained_turns_without_assembly_labels_input_tokens": retained_only_tokens,
            "history_context_chars": assembly.manifest["assembled_chars"],
            "kept_items": len(included),
            "dropped_count": len(dropped),
            "truncated_count": assembly.manifest["truncated_count"],
            "dropped_items": [{"turn": turn, "reason": reason} for turn, reason in dropped.items()],
            "truncated_items": truncated,
            "retained_key_facts": kept,
            "key_fact_retention_rate": kept / len(facts),
        },
        "count_method": baseline_count.method,
        "input_token_reduction_rate": 1 - clipped_count.tokens / baseline_count.tokens,
        "key_facts": facts,
    }


def build_report():
    raw = DATASET.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != FROZEN_DATASET_SHA256:
        raise ValueError(f"数据集 SHA-256 与标注锁定值不同：{digest}")
    baseline = json.loads(BASELINE_REPORT.read_text(encoding="utf-8"))
    if baseline["dataset"]["sha256"] != digest:
        raise ValueError("v1 报告与冻结数据集不匹配")
    sessions = [json.loads(line) for line in raw.splitlines()]
    source = DATASET.with_name("meetingmind_real_v1_sources.jsonl")

    # model_construct 使用 Settings 类定义的默认值，不读取本机环境变量或 dotenv。
    defaults = Settings.model_construct()
    with (
        patch.object(context_assembler, "settings", defaults),
        patch.object(token_budget_ledger, "settings", defaults),
    ):
        assembler = context_assembler.ContextAssembler()
        counter = token_budget_ledger.ModelTokenCounter()
        details = [measure(s, assembler, counter, defaults.LLM_MODEL) for s in sessions]

    a = [detail["baseline_a"]["input_tokens"] for detail in details]
    b = [detail["assembled_b"]["input_tokens"] for detail in details]
    median_a, median_b = statistics.median(a), statistics.median(b)
    mean_a, mean_b = statistics.mean(a), statistics.mean(b)
    facts = [fact for detail in details for fact in detail["key_facts"]]
    loss_reasons = Counter(fact["loss_reason"] for fact in facts if not fact["present_in_b"])
    lost = sum(loss_reasons.values())
    retained = len(facts) - lost
    retention = retained / len(facts)
    overhead = [
        result["input_tokens"] - result["retained_turns_without_assembly_labels_input_tokens"]
        for detail in details
        if (result := detail["assembled_b"])["retained_turns_without_assembly_labels_input_tokens"] is not None
    ]
    limitations = [
        "12段对话由8场 AliMeeting-Eval 真实转录片段改写构造，部分来源会议重复；不是线上对话日志。",
        "全量历史直送组装器是压力对照；线上通常只送最近3轮，还可能带任务约束和证据，因此不能把降幅外推为线上成本节省。",
        "逐字保留仅测上下文是否含标注文本；不能衡量语义等价、模型回答正确率或从检索中补回事实的能力。",
        "Token 使用配置模型的启发式估计，不是 Qwen tokenizer 或供应商 usage，且未计系统提示、消息协议开销或生成。",
        "词面匹配可能因同义改写而漏掉相关轮次，也可能因常见措辞优先保留无关轮次；条目上限仍会牺牲部分近期或低词面重合的历史。",
    ]
    if retention < 0.9:
        reasons = "、".join(f"{reason} {count} 条" for reason, count in loss_reasons.items())
        limitations.append(f"事实保留率低于90%：丢失{lost}条（{reasons}）。")
    return {
        "schema_version": "memory-budget-control.v2",
        "code_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=BACKEND, text=True
        ).strip(),
        "code_commit_scope": "被测工作区的 HEAD；v2 结果包含工作区中未提交的组装器和脚本改动。",
        "dataset": {
            "path": DATASET.relative_to(BACKEND.parent).as_posix(),
            "sha256": digest,
            "annotation_sha256_locked_before_script": FROZEN_DATASET_SHA256,
            "source_path": source.relative_to(BACKEND.parent).as_posix(),
            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "construction": "基于真实会议转录片段改写构造；每个历史问答附原始引用 ID，关键事实在测量脚本编写前标注。",
        },
        "method": METHOD,
        "count_model": defaults.LLM_MODEL,
        "count_method": details[0]["count_method"],
        "budget": {
            "source": "Settings 类代码默认值（无运行环境覆盖）",
            "max_context_chars": defaults.LLM_MAX_CONTEXT_CHARS,
            "max_item_chars": assembler.max_item_chars,
            "max_items": assembler.max_items,
            "max_chunks_per_document": assembler.max_chunks_per_document,
            "anchor_max_chars": assembler.anchor_max_chars,
        },
        "summary": {
            "sessions": len(sessions),
            "source_meetings": len({s["meeting_id"] for s in sessions}),
            "turn_distribution_including_final_question": dict(sorted(Counter(
                detail["turn_count_including_final_question"] for detail in details
            ).items())),
            "input_tokens": {
                "a_median": median_a,
                "b_median": median_b,
                "median_reduction_rate": 1 - median_b / median_a,
                "median_paired_reduction_rate": statistics.median(
                    detail["input_token_reduction_rate"] for detail in details
                ),
                "a_mean": mean_a,
                "b_mean": mean_b,
                "mean_reduction_rate": 1 - mean_b / mean_a,
                "reduction_denominators": "中位数和均值降幅以 A 的同类统计量为分母；逐会话降幅以该会话的 A 为分母。",
                "b_higher_than_a_session_count": sum(after > before for before, after in zip(a, b)),
                "assembly_label_overhead": {
                    "method": "仅对 B 无截断的会话，比较 B 与同序保留轮次去掉组装标签和包装后的计数；两者都含最终问题。",
                    "sessions": len(overhead),
                    "median_tokens": statistics.median(overhead) if overhead else None,
                },
            },
            "key_facts": {
                "total": len(facts),
                "a_retained": len(facts),
                "a_retention_rate": 1.0,
                "b_retained": retained,
                "b_lost": lost,
                "b_retention_rate": retention,
                "loss_reasons": dict(loss_reasons),
            },
            "b_dropped_items": sum(d["assembled_b"]["dropped_count"] for d in details),
            "b_drop_reasons": dict(Counter(
                item["reason"] for detail in details for item in detail["assembled_b"]["dropped_items"]
            )),
            "b_truncated_items": sum(d["assembled_b"]["truncated_count"] for d in details),
        },
        "comparison": compare_versions(baseline["sessions"], details),
        "sessions": details,
        "limitations": limitations,
    }


def compare_versions(v1, v2):
    def metrics(details):
        facts = [fact for session in details for fact in session["key_facts"]]
        median_a = statistics.median(s["baseline_a"]["input_tokens"] for s in details)
        median_b = statistics.median(s["assembled_b"]["input_tokens"] for s in details)
        retained = sum(fact["present_in_b"] for fact in facts)
        return {
            "a_input_tokens_median": median_a,
            "b_input_tokens_median": median_b,
            "b_input_tokens_median_change_vs_a": median_b / median_a - 1,
            "retained_key_facts": retained,
            "total_key_facts": len(facts),
            "key_fact_retention_rate": retained / len(facts),
            "fact_loss_reasons": dict(Counter(
                fact["loss_reason"] for fact in facts if not fact["present_in_b"]
            )),
            "item_drop_reasons": dict(Counter(
                item["reason"] for session in details for item in session["assembled_b"]["dropped_items"]
            )),
        }

    def index_facts(details):
        return {
            (session["session_id"], fact["turn"], fact["text"]): fact
            for session in details for fact in session["key_facts"]
        }

    before, after = index_facts(v1), index_facts(v2)
    if before.keys() != after.keys():
        raise ValueError("v1 与 v2 的事实标注不匹配")
    return {
        "v1_report": BASELINE_REPORT.relative_to(BACKEND.parent).as_posix(),
        "v1": metrics(v1),
        "v2": metrics(v2),
        "recovered_facts": [
            {"session_id": key[0], **fact, "v1_loss_reason": before[key]["loss_reason"]}
            for key, fact in after.items() if fact["present_in_b"] and not before[key]["present_in_b"]
        ],
        "newly_lost_facts": [
            {"session_id": key[0], **fact}
            for key, fact in after.items() if not fact["present_in_b"] and before[key]["present_in_b"]
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=REPORT)
    args = parser.parse_args()
    if args.output.resolve() in {DATASET.resolve(), BASELINE_REPORT.resolve()}:
        parser.error("--output 不能覆盖冻结数据集或 v1 报告")
    report = build_report()
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps(report["summary"], ensure_ascii=True))


if __name__ == "__main__":
    main()
