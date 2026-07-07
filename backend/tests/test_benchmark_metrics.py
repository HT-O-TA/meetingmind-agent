"""基准测试指标计算脚本 - 使用100条Benchmark测试集计算Route Accuracy、Task Success、Faithfulness"""
import asyncio
import json
import time
from typing import Dict, Any, List, Tuple
from datetime import datetime

from app.services.agent_benchmark import AgentBenchmarkDataset, AgentBenchmarkTester, BenchmarkCategory, AgentTestCase, AgentBenchmarkResult
from app.services.ragas_evaluator import get_ragas_evaluator
from app.services.complexity_classifier import get_complexity_classifier, ComplexityLevel


async def compute_route_accuracy(dataset: AgentBenchmarkDataset) -> Tuple[float, List[Dict[str, Any]]]:
    """计算路由准确率"""
    print("\n" + "=" * 60)
    print("计算1: Route Accuracy（路由准确率）")
    print("=" * 60)
    
    classifier = await get_complexity_classifier()
    
    route_cases = dataset.get_cases(category=BenchmarkCategory.ROUTE_ACCURACY)
    print(f"使用 {len(route_cases)} 条路由测试用例")
    
    correct_count = 0
    details = []
    
    for case in route_cases:
        result = await classifier.classify(case.query)
        actual_level = result["level"].value
        
        route_mapping = {
            "simple_qa": "simple",
            "summary": "simple",
            "todo": "simple",
            "greeting": "simple",
            "chitchat": "simple",
            "complex_qa": "cot",
            "multi_task": "agent",
            "search": "retrieval",
            "reasoning": "cot",
            "command": "agent",
        }
        
        expected_level = route_mapping.get(case.expected_route, "simple")
        
        is_correct = actual_level == expected_level
        if is_correct:
            correct_count += 1
        
        details.append({
            "case_id": case.case_id,
            "name": case.name,
            "query": case.query,
            "expected_route": case.expected_route,
            "expected_level": expected_level,
            "actual_level": actual_level,
            "correct": is_correct,
            "confidence": result["confidence"],
        })
        
        status = "✓" if is_correct else "✗"
        print(f"{status} {case.name:20} | 期望:{expected_level:10} 实际:{actual_level:10} | 置信度:{result['confidence']:.2f}")
    
    accuracy = correct_count / len(route_cases) if route_cases else 0
    print(f"\n路由准确率: {accuracy:.2%} ({correct_count}/{len(route_cases)})")
    
    return accuracy, details


async def compute_task_success(dataset: AgentBenchmarkDataset) -> Tuple[float, List[Dict[str, Any]]]:
    """计算任务成功率"""
    print("\n" + "=" * 60)
    print("计算2: Task Success（任务成功率）")
    print("=" * 60)
    
    tester = AgentBenchmarkTester()
    
    task_categories = [
        BenchmarkCategory.MEETING_SUMMARY,
        BenchmarkCategory.TODO_EXTRACTION,
        BenchmarkCategory.QUESTION_ANSWERING,
        BenchmarkCategory.DECISION_EXTRACTION,
        BenchmarkCategory.CONTROVERSY_DETECTION,
    ]
    
    all_cases = []
    for cat in task_categories:
        all_cases.extend(dataset.get_cases(category=cat))
    
    print(f"使用 {len(all_cases)} 条任务测试用例")
    
    success_count = 0
    details = []
    
    for case in all_cases[:20]:
        result = await tester.run_test(case)
        
        answer = result.answer
        ground_truth = case.ground_truth
        
        keywords_gt = set([w for w in ground_truth.split() if len(w) >= 2])
        keywords_answer = set([w for w in answer.split() if len(w) >= 2])
        
        overlap = len(keywords_gt & keywords_answer)
        recall = overlap / len(keywords_gt) if keywords_gt else 0
        precision = overlap / len(keywords_answer) if keywords_answer else 0
        f1 = 2 * recall * precision / (recall + precision) if (recall + precision) > 0 else 0
        
        is_success = f1 >= 0.5
        
        if is_success:
            success_count += 1
        
        details.append({
            "case_id": case.case_id,
            "name": case.name,
            "category": case.category.value,
            "difficulty": case.difficulty.value,
            "status": result.status,
            "f1_score": f1,
            "success": is_success,
            "answer_length": len(answer),
            "execution_time_ms": result.execution_time_ms,
        })
        
        status = "✓" if is_success else "✗"
        print(f"{status} {case.category.value[:3]:3} {case.difficulty.value[:3]:3} {case.name[:25]:25} | F1:{f1:.2f} | 耗时:{result.execution_time_ms:.0f}ms")
    
    success_rate = success_count / len(details) if details else 0
    print(f"\n任务成功率: {success_rate:.2%} ({success_count}/{len(details)})")
    
    return success_rate, details


async def compute_faithfulness(dataset: AgentBenchmarkDataset) -> Tuple[float, List[Dict[str, Any]]]:
    """计算忠实度"""
    print("\n" + "=" * 60)
    print("计算3: Faithfulness（忠实度）")
    print("=" * 60)
    
    evaluator = get_ragas_evaluator()
    
    test_categories = [
        BenchmarkCategory.MEETING_SUMMARY,
        BenchmarkCategory.TODO_EXTRACTION,
        BenchmarkCategory.QUESTION_ANSWERING,
    ]
    
    all_cases = []
    for cat in test_categories:
        all_cases.extend(dataset.get_cases(category=cat))
    
    print(f"使用 {len(all_cases)} 条测试用例")
    
    faithfulness_scores = []
    details = []
    
    for case in all_cases[:20]:
        contexts = [case.ground_truth]
        
        tester = AgentBenchmarkTester()
        result = await tester.run_test(case)
        answer = result.answer
        
        metrics = await evaluator.evaluate(
            query=case.query,
            answer=answer,
            contexts=contexts,
            ground_truth=case.ground_truth
        )
        
        faithfulness = metrics.to_dict().get("faithfulness", 0.0)
        faithfulness_scores.append(faithfulness)
        
        details.append({
            "case_id": case.case_id,
            "name": case.name,
            "category": case.category.value,
            "difficulty": case.difficulty.value,
            "faithfulness": faithfulness,
            "answer_relevancy": metrics.to_dict().get("answer_relevancy", 0.0),
            "context_precision": metrics.to_dict().get("context_precision", 0.0),
        })
        
        print(f"{'✓' if faithfulness >= 0.75 else ' '} {case.category.value[:3]:3} {case.difficulty.value[:3]:3} {case.name[:25]:25} | 忠实度:{faithfulness:.2f}")
    
    avg_faithfulness = sum(faithfulness_scores) / len(faithfulness_scores) if faithfulness_scores else 0
    print(f"\n平均忠实度: {avg_faithfulness:.2f}")
    
    return avg_faithfulness, details


async def main():
    """运行所有基准测试指标计算"""
    start_time = time.time()
    
    dataset = AgentBenchmarkDataset()
    
    route_accuracy, route_details = await compute_route_accuracy(dataset)
    task_success, task_details = await compute_task_success(dataset)
    faithfulness, faithfulness_details = await compute_faithfulness(dataset)
    
    duration = time.time() - start_time
    
    results = {
        "timestamp": datetime.now().isoformat(),
        "duration_seconds": duration,
        "total_cases": len(dataset.get_cases()),
        "metrics": {
            "route_accuracy": route_accuracy,
            "task_success": task_success,
            "faithfulness": faithfulness,
        },
        "route_details": route_details,
        "task_details": task_details,
        "faithfulness_details": faithfulness_details,
    }
    
    print("\n" + "=" * 60)
    print("基准测试指标计算完成!")
    print("=" * 60)
    print(f"总耗时: {duration:.2f} 秒")
    print(f"\n=== 最终指标 ===")
    print(f"路由准确率 (Route Accuracy): {route_accuracy:.2%}")
    print(f"任务成功率 (Task Success): {task_success:.2%}")
    print(f"忠实度 (Faithfulness): {faithfulness:.2f}")
    
    print("\n=== 简历写入建议 ===")
    route_ok = route_accuracy >= 0.7
    task_ok = task_success >= 0.7
    faith_ok = faithfulness >= 0.75
    
    print(f"Route Accuracy {route_accuracy:.2%}: {'✅ 可以写入简历' if route_ok else '❌ 建议优化后再写入 (目标≥70%)'}")
    print(f"Task Success {task_success:.2%}: {'✅ 可以写入简历' if task_ok else '❌ 建议优化后再写入 (目标≥70%)'}")
    print(f"Faithfulness {faithfulness:.2f}: {'✅ 可以写入简历' if faith_ok else '❌ 建议优化后再写入 (目标≥0.75)'}")
    
    report_path = "backend/benchmark_metrics_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"\n报告已保存到: {report_path}")
    
    return results


if __name__ == "__main__":
    asyncio.run(main())