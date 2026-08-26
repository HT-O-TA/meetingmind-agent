import pytest

from app.services.semantic_chunker import ChunkingConfig, ChunkingStrategy, SemanticChunker


def _chunker(**overrides):
    return SemanticChunker(
        config=ChunkingConfig(
            min_chunk_size=overrides.get("min_chunk_size", 20),
            max_chunk_size=overrides.get("max_chunk_size", 80),
            chunk_overlap=overrides.get("chunk_overlap", 0),
            semantic_threshold=overrides.get("semantic_threshold", 0.2),
        )
    )


def test_only_formal_strategy_is_exposed():
    assert list(ChunkingStrategy) == [ChunkingStrategy.SPEAKER_AWARE_HYBRID]


@pytest.mark.asyncio
async def test_speaker_path_preserves_speaker_and_timestamp_evidence():
    text = (
        "[00:01.50] speaker_0: 项目预算需要财务确认。\n"
        "[00:05.00] speaker_0: 财务将在周五前完成审核。\n"
        "[00:09.25] speaker_1: 技术团队随后更新排期。"
    )

    chunks = await _chunker(min_chunk_size=200, max_chunk_size=200).chunk_document(text, "meeting-7")

    assert len(chunks) == 1
    assert chunks[0].chunk_id == "meeting-7_0"
    assert chunks[0].metadata["source"] == "speaker_aware_hybrid"
    assert chunks[0].metadata["speakers"] == ["speaker_0", "speaker_1"]
    assert chunks[0].metadata["speaker_name"] is None
    assert chunks[0].metadata["time_offset"] == 1.5
    assert chunks[0].metadata["last_time_offset"] == 9.25


@pytest.mark.asyncio
async def test_numeric_speaker_and_tone_only_line_are_supported():
    text = (
        "[00:01.00] 0157: 嗯嗯。\n"
        "[00:02.00] 0157: 负责人将在明天提交方案。"
    )

    chunks = await _chunker().chunk_document(text, "meeting-8")

    assert len(chunks) == 1
    assert "嗯嗯" not in chunks[0].content
    assert chunks[0].metadata["speaker_name"] == "0157"
    assert chunks[0].metadata["time_offset"] == 2.0


@pytest.mark.asyncio
async def test_plain_text_uses_explicit_local_fallback_and_overlap():
    text = (
        "项目风险包括延期和资源不足。项目风险需要每周跟进。\n\n"
        "菜谱推荐番茄炒蛋和青椒肉丝。烹饪步骤需要控制火候。"
    )

    chunks = await _chunker(chunk_overlap=4).chunk_document(text, "plain")

    assert len(chunks) == 2
    assert chunks[0].metadata["source"] == "local_semantic_fallback"
    assert chunks[0].metadata["has_speaker_info"] is False
    assert chunks[1].content.startswith(chunks[0].content[-4:])


@pytest.mark.asyncio
async def test_plain_long_sentence_has_bounded_base_segments():
    chunks = await _chunker(max_chunk_size=30).chunk_document("测试内容" * 25, "long")

    assert len(chunks) >= 3
    assert all(chunk.content for chunk in chunks)
