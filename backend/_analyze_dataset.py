"""检查评估数据集中不同类型问题的检索效果"""
import sys
sys.path.insert(0, '.')
import os
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from tests.rag.rag_eval_dataset import get_eval_dataset

dataset = get_eval_dataset()

# 查看不同类别的问题
print("=== 问题类型示例 ===")
for i, item in enumerate(dataset):
    q = item['question']
    if '讨论的主要内容' not in q and '做出了哪些重要决策' not in q and '提到了哪些' not in q:
        print(f"\nQ{i} (id={item['id']}): {q}")
        print(f"   doc_ids: {item.get('relevant_doc_ids')}")
        print(f"   answer: {item.get('expected_answer', '')[:100]}")
        if i > 230:
            break

# 查看expected_answer是否包含文档内容
print("\n\n=== 前3个问题的 expected_answer ===")
for item in dataset[:3]:
    print(f"\nQ: {item['question']}")
    print(f"doc_ids: {item.get('relevant_doc_ids')}")
    print(f"answer: {item.get('expected_answer', '')[:200]}")
