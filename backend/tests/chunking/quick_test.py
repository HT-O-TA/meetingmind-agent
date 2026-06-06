"""
快速测试脚本 - 只测试少量参数组合
用于验证实验代码是否正常工作
"""

import sys
sys.path.insert(0, str(__file__).rsplit('/', 1)[0] if '/' in __file__ else '.')

from speaker_aware_parameter_tuning import SpeakerAwareHybridChunker, ParameterTuningExperiment
from pathlib import Path
from tqdm import tqdm
import json
import time


def test_chunker():
    """快速测试分块器"""
    print("=" * 60)
    print("测试 SpeakerAwareHybridChunker (带语气词过滤)")
    print("=" * 60)

    # 测试文档
    test_content = """[00:01.00] 1: 今天我们来讨论一下产品的新版本计划。
[00:05.00] 2: 好的，我先介绍一下市场反馈情况。
[00:08.00] 2: 用户普遍反映界面需要优化。
[00:12.00] 1: 是的，我们已经收集了很多这方面的建议。
[00:15.00] 1: 另外，性能问题也需要优先解决。
[00:20.00] 3: 我同意，响应速度确实太慢了。
[00:23.00] 3: 我建议先做一次全面的性能测试。
[00:28.00] 2: 可以，我来安排测试资源。
[00:32.00] 1: 好的，那我们就按照这个计划执行。
[00:35.00] 1: 嗯，嗯，嗯。"""

    chunker = SpeakerAwareHybridChunker(
        min_chunk_size=50,
        max_chunk_size=200,
        chunk_overlap=30,
        semantic_threshold=0.6,
        speaker_switch_bonus=0.2
    )

    chunks, metadata = chunker.chunk_document(test_content)

    print(f"\n原始内容行数: {len(test_content.split(chr(10)))}")
    print(f"过滤后分块数: {len(chunks)}")
    print(f"\n元数据: {json.dumps(metadata, indent=2, ensure_ascii=False)}")
    print("\n分块结果:")
    for i, chunk in enumerate(chunks, 1):
        print(f"  块 {i} ({len(chunk)} 字符): {chunk[:60]}..." if len(chunk) > 60 else f"  块 {i} ({len(chunk)} 字符): {chunk}")


def test_tone_filter():
    """测试语气词过滤功能"""
    print("\n" + "=" * 60)
    print("测试语气词过滤")
    print("=" * 60)

    chunker = SpeakerAwareHybridChunker()

    test_cases = [
        "嗯嗯嗯，好的好的",
        "对对对，是是是",
        "今天我们讨论市场反馈",
        "啊啊啊啊啊",
        "我觉得这个方案不错",
    ]

    for text in test_cases:
        is_tone = chunker._is_tone_only(text)
        filtered = chunker._filter_tone_words(text)
        print(f"原文: {text}")
        print(f"  -> 纯语气词: {is_tone}")
        print(f"  -> 过滤后: '{filtered}'")
        print()


def run_small_experiment():
    """运行小规模参数实验（只有少量组合）"""
    print("\n" + "=" * 60)
    print("运行小规模参数调优实验")
    print("=" * 60)

    data_dir = Path(__file__).parent / "data" / "meeting_docs_with_speaker"

    # 使用新的小规模参数网格
    from itertools import product
    
    small_param_grid = {
        'min_chunk_size': [50, 80],
        'max_chunk_size': [300, 400],
        'chunk_overlap': [30, 50],
        'semantic_threshold': [0.6],
        'speaker_switch_bonus': [0.2]
    }

    # 加载少量文档
    docs = []
    doc_files = sorted(list(data_dir.glob('*.md')))[:5]  # 只用5个文档
    for file_path in tqdm(doc_files, desc="加载文档"):
        try:
            content = file_path.read_text(encoding='utf-8')
            docs.append((file_path.name, content))
        except:
            pass

    print(f"\n文档数: {len(docs)}")

    combinations = list(product(
        small_param_grid['min_chunk_size'],
        small_param_grid['max_chunk_size'],
        small_param_grid['chunk_overlap'],
        small_param_grid['semantic_threshold'],
        small_param_grid['speaker_switch_bonus']
    ))

    # 过滤无效组合
    valid_combos = [(m, mx, o, t, b) for m, mx, o, t, b in combinations if m < mx]
    print(f"参数组合数: {len(valid_combos)}")
    print("\n开始实验...")

    results = []
    for min_size, max_size, overlap, threshold, bonus in tqdm(valid_combos, desc="参数组合"):
        chunker = SpeakerAwareHybridChunker(
            min_chunk_size=min_size,
            max_chunk_size=max_size,
            chunk_overlap=overlap,
            semantic_threshold=threshold,
            speaker_switch_bonus=bonus
        )

        all_chunks = []
        start = time.time()

        for _, content in docs:
            chunks, _ = chunker.chunk_document(content)
            all_chunks.extend(chunks)

        elapsed = time.time() - start
        avg_size = sum(len(c) for c in all_chunks) / len(all_chunks) if all_chunks else 0
        avg_info_density = sum(chunker._count_info_chars(c) / max(len(c), 1) for c in all_chunks) / len(all_chunks) if all_chunks else 0

        results.append({
            'config': {
                'min': min_size, 'max': max_size, 'overlap': overlap,
                'threshold': threshold, 'bonus': bonus
            },
            'chunk_count': len(all_chunks),
            'avg_size': avg_size,
            'info_density': avg_info_density,
            'time': elapsed
        })

    # 保存结果
    output_path = data_dir.parent / "quick_test_results.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n结果已保存到: {output_path}")
    print(f"\n实验结果 (按块数量排序):")
    results.sort(key=lambda x: x['chunk_count'])
    print(f"{'min':<5} {'max':<5} {'overlap':<7} {'threshold':<10} {'块数':<8} {'平均大小':<10} {'信息密度':<10}")
    print("-" * 60)
    for r in results:
        cfg = r['config']
        print(f"{cfg['min']:<5} {cfg['max']:<5} {cfg['overlap']:<7} {cfg['threshold']:<10.2f} {r['chunk_count']:<8} {r['avg_size']:<10.0f} {r['info_density']:<10.2%}")


if __name__ == "__main__":
    test_chunker()
    test_tone_filter()
    run_small_experiment()
