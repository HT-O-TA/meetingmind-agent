"""构建 prompt 调参开发集：只取 ai_reviews 中不属于冻结评测集的单元。

- 约束：AI 银标 accept 55 / reject 143，平衡抽样。
- 待办：银标全是 reject，另加少量人工撰写的"明确行动"正例，补正例缺口（标 source=synthetic）。
评测集 100 条不参与任何调参；调参只看本开发集的指标。
"""
import json
import random
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
D = BACKEND / "evaluation/datasets"
OUT = D / "prompt_dev_v1.jsonl"

# 口语转写风格的正例，assignee 统一用说话人代号，与真实候选分布一致；只用于开发集。
SYNTHETIC_TODOS = [
    ("这个接口文档周五之前你给我整理出来，发群里。", "speaker_2", [{"content": "周五前整理接口文档并发到群里。", "assignee": "", "deadline": ""}]),
    ("那回头你跟财务那边对一下这个报销的流程，嗯，对一下。", "speaker_1", [{"content": "与财务核对报销流程。", "assignee": "", "deadline": ""}]),
    ("测试环境这块呢小刘负责搭起来，然后下周一大家就能用。", "N_SPK8021", [{"content": "搭建测试环境。", "assignee": "", "deadline": ""}]),
    ("我们会后把客户反馈汇总一下，再约个时间过一遍方案。", "speaker_3", [{"content": "汇总客户反馈。", "assignee": "", "deadline": ""}, {"content": "约时间评审方案。", "assignee": "", "deadline": ""}]),
    ("对对对，这个样品你先寄三份过去，让他们先试一下效果。", "N_SPK8013", [{"content": "寄送三份样品给对方试用。", "assignee": "", "deadline": ""}]),
    ("那排期这个事情你去跟产品确认一下，别拖。", "speaker_4", [{"content": "与产品确认排期。", "assignee": "", "deadline": ""}]),
]


def main():
    ev = [json.loads(l) for l in (D / "meetingmind_real_v1_evaluation.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    frozen = {r["source_unit_id"] for r in ev}
    ar = [json.loads(l) for l in (D / "meetingmind_real_v1_ai_reviews.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    pool = [r for r in ar if r["unit_id"] not in frozen and r["unit_type"] in ("todo", "constraint")]
    rng = random.Random(20260926)
    rows = []
    c_acc = [r for r in pool if r["unit_type"] == "constraint" and r["decision"] == "accept"]
    c_rej = [r for r in pool if r["unit_type"] == "constraint" and r["decision"] == "reject"]
    t_rej = [r for r in pool if r["unit_type"] == "todo" and r["decision"] == "reject"]
    for r in rng.sample(c_acc, 20) + rng.sample(c_rej, 20):
        cand = {k: r["candidate"][k] for k in ("kind", "text")}
        gold = [{"kind": r["corrected"]["kind"], "text": r["corrected"]["text"]}] if r["decision"] == "accept" else []
        rows.append({"id": f"dev-{r['unit_id']}", "unit_type": "constraint", "source": "ai_silver", "candidate": cand, "expected": gold})
    for r in rng.sample(t_rej, 20):
        cand = {k: r["candidate"].get(k, "") for k in ("content", "assignee", "deadline")}
        rows.append({"id": f"dev-{r['unit_id']}", "unit_type": "todo", "source": "ai_silver", "candidate": cand, "expected": []})
    for i, (content, who, gold) in enumerate(SYNTHETIC_TODOS):
        rows.append({"id": f"dev-synthetic-todo-{i}", "unit_type": "todo", "source": "synthetic",
                     "candidate": {"content": content, "assignee": who, "deadline": ""}, "expected": gold})
    assert not ({r["id"].removeprefix("dev-") for r in rows} & frozen)
    OUT.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print(len(rows), OUT.name)


if __name__ == "__main__":
    main()
