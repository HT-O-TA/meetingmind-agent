import pytest

from app.services.semantic_chunker import ChunkingConfig, ChunkingStrategy, SemanticChunker


@pytest.mark.asyncio
async def test_fixed_size_chunking_uses_overlap():
    chunker = SemanticChunker(config=ChunkingConfig(
        strategy=ChunkingStrategy.FIXED_SIZE,
        max_chunk_size=10,
        chunk_overlap=3,
        build_hierarchy=False,
    ))

    chunks = await chunker.chunk_document("abcdefghijklmnopqrstuvwxyz", "doc")

    assert [chunk.content for chunk in chunks[:2]] == ["abcdefghij", "hijklmnopq"]
    assert all(chunk.metadata["source"] == "fixed_size" for chunk in chunks)


@pytest.mark.asyncio
async def test_paragraph_chunking_keeps_paragraph_boundaries():
    chunker = SemanticChunker(config=ChunkingConfig(
        strategy=ChunkingStrategy.PARAGRAPH,
        max_chunk_size=80,
        chunk_overlap=0,
        build_hierarchy=False,
    ))

    text = "第一段介绍项目背景。\n\n第二段说明技术方案。\n\n第三段记录结论。"
    chunks = await chunker.chunk_document(text, "doc")

    assert len(chunks) == 1
    assert "第一段介绍项目背景" in chunks[0].content
    assert chunks[0].metadata["source"] == "paragraph"


@pytest.mark.asyncio
async def test_recursive_chunking_splits_long_text_by_sentence():
    chunker = SemanticChunker(config=ChunkingConfig(
        strategy=ChunkingStrategy.RECURSIVE,
        max_chunk_size=24,
        chunk_overlap=0,
        build_hierarchy=False,
    ))

    text = "这是第一句话。这是第二句话。这是第三句话。这是第四句话。"
    chunks = await chunker.chunk_document(text, "doc")

    assert len(chunks) > 1
    assert all(len(chunk.content) <= 24 for chunk in chunks)
    assert all(chunk.metadata["source"] == "recursive" for chunk in chunks)


@pytest.mark.asyncio
async def test_semantic_strategy_uses_local_similarity_when_llm_disabled():
    chunker = SemanticChunker(config=ChunkingConfig(
        strategy=ChunkingStrategy.SEMANTIC,
        min_chunk_size=20,
        max_chunk_size=120,
        chunk_overlap=0,
        semantic_threshold=0.2,
        use_llm_split=False,
        build_hierarchy=False,
    ))

    text = (
        "项目风险包括延期和资源不足。项目风险需要每周跟进。\n\n"
        "菜谱推荐番茄炒蛋和青椒肉丝。烹饪步骤需要控制火候。"
    )
    chunks = await chunker.chunk_document(text, "doc")

    assert len(chunks) == 2
    assert "项目风险" in chunks[0].content
    assert "菜谱推荐" in chunks[1].content
    assert all(chunk.metadata["source"] == "local_semantic" for chunk in chunks)


@pytest.mark.asyncio
async def test_hybrid_strategy_uses_semantic_boundaries_by_default():
    chunker = SemanticChunker(config=ChunkingConfig(
        strategy=ChunkingStrategy.SEMANTIC_HYBRID,
        min_chunk_size=20,
        max_chunk_size=120,
        chunk_overlap=0,
        semantic_threshold=0.2,
        use_llm_split=False,
        build_hierarchy=False,
    ))

    text = (
        "会议讨论预算审批和项目排期。预算审批需要财务确认。\n\n"
        "天气预报显示周末有雨。出行需要携带雨具。"
    )
    chunks = await chunker.chunk_document(text, "doc")

    assert len(chunks) == 2
    assert "预算审批" in chunks[0].content
    assert "天气预报" in chunks[1].content
    assert all(chunk.metadata["source"] == "semantic_hybrid" for chunk in chunks)
