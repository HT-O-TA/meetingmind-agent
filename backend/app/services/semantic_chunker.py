"""会议文档的唯一正式分块器：说话人感知 + 本地语义近似。"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.core.logger import app_logger


@dataclass
class Chunk:
    """可入库的文档块。"""

    chunk_id: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class ChunkingStrategy(str, Enum):
    """仓库只保留经正式入库链路调用的策略。"""

    SPEAKER_AWARE_HYBRID = "speaker_aware_hybrid"


@dataclass
class ChunkingConfig:
    strategy: ChunkingStrategy = ChunkingStrategy.SPEAKER_AWARE_HYBRID
    min_chunk_size: int = 50
    max_chunk_size: int = 300
    chunk_overlap: int = 30
    semantic_threshold: float = 0.7


@dataclass(frozen=True)
class _Utterance:
    speaker: str
    text: str
    time_offset: Optional[float]


class SemanticChunker:
    """保留说话人和时间证据，无标记文本明确降级为本地分块。"""

    _SPEAKER_LINE = re.compile(
        r"^\[([^\]]+)\]\s*([^\s:：]+)\s*[:：]\s*(.+)$"
    )
    _TONE_WORDS = {
        "嗯", "啊", "哦", "唉", "对", "好", "是", "呃", "哎", "额", "行",
        "嗯哼", "啊哈", "对对对", "嗯嗯", "嗯嗯嗯", "是是是", "啊啊",
        "嗯嗯嗯嗯", "行行行", "可以可以", "好好好",
    }
    _STOPWORDS = {
        "的", "了", "和", "与", "及", "或", "是", "在", "有", "为", "对", "中",
        "需要", "进行", "包括", "以及", "一个", "这个", "那个", "我们", "他们",
        "the", "a", "an", "and", "or", "of", "to", "in", "for", "with", "is", "are",
    }

    def __init__(self, config: Optional[ChunkingConfig] = None):
        self._config = config or ChunkingConfig()

    @staticmethod
    def _parse_time_offset(value: str) -> Optional[float]:
        try:
            parts = [float(part) for part in value.strip().split(":")]
        except (TypeError, ValueError):
            return None
        if len(parts) == 2:
            return parts[0] * 60 + parts[1]
        if len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
        return None

    @classmethod
    def _is_tone_only(cls, content: str) -> bool:
        cleaned = re.sub(r"[.!?。！？，、；：\s]+", "", content or "")
        if len(cleaned) < 2:
            return True
        for tone in sorted(cls._TONE_WORDS, key=len, reverse=True):
            cleaned = cleaned.replace(tone, "")
        return not cleaned

    @classmethod
    def _parse_speaker_document(cls, content: str) -> List[_Utterance]:
        utterances: List[_Utterance] = []
        for raw_line in (content or "").splitlines():
            match = cls._SPEAKER_LINE.match(raw_line.strip())
            if not match:
                continue
            text = match.group(3).strip()
            if cls._is_tone_only(text):
                continue
            utterances.append(
                _Utterance(
                    speaker=match.group(2),
                    text=text,
                    time_offset=cls._parse_time_offset(match.group(1)),
                )
            )
        return utterances

    @classmethod
    def _tokens(cls, text: str) -> List[str]:
        try:
            import jieba

            raw_tokens = jieba.lcut(text)
        except Exception:
            raw_tokens = re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z0-9_]{2,}", text)
        return [
            token.lower().strip()
            for token in raw_tokens
            if token.strip()
            and token.lower().strip() not in cls._STOPWORDS
            and re.search(r"[\u4e00-\u9fffa-zA-Z0-9]", token)
        ]

    @classmethod
    def _similarity(cls, left: str, right: str) -> float:
        left_counts = Counter(cls._tokens(left))
        right_counts = Counter(cls._tokens(right))
        if not left_counts or not right_counts:
            return 0.0
        dot = sum(left_counts[token] * right_counts[token] for token in left_counts.keys() & right_counts.keys())
        left_norm = math.sqrt(sum(value * value for value in left_counts.values()))
        right_norm = math.sqrt(sum(value * value for value in right_counts.values()))
        return dot / (left_norm * right_norm) if left_norm and right_norm else 0.0

    def _add_overlap(self, chunks: Sequence[str]) -> List[str]:
        if self._config.chunk_overlap <= 0 or len(chunks) < 2:
            return list(chunks)
        result = [chunks[0]]
        for index in range(1, len(chunks)):
            prefix = chunks[index - 1][-self._config.chunk_overlap :]
            result.append(f"{prefix} {chunks[index]}".strip())
        return result

    def _plain_units(self, text: str) -> List[str]:
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
        units: List[str] = []
        for paragraph in paragraphs or [text.strip()]:
            if len(paragraph) <= self._config.max_chunk_size:
                units.append(paragraph)
                continue
            sentences = [
                sentence.strip()
                for sentence in re.findall(r"[^.!?。！？\n]+[.!?。！？]?", paragraph)
                if sentence.strip()
            ]
            for sentence in sentences or [paragraph]:
                if len(sentence) <= self._config.max_chunk_size:
                    units.append(sentence)
                else:
                    units.extend(
                        sentence[start : start + self._config.max_chunk_size]
                        for start in range(0, len(sentence), self._config.max_chunk_size)
                    )
        return units

    def _group_plain_text(self, text: str) -> List[str]:
        units = self._plain_units(text)
        if not units:
            return []
        groups: List[str] = []
        current = units[0]
        for unit in units[1:]:
            candidate = f"{current}\n\n{unit}"
            related = self._similarity(current, unit) >= self._config.semantic_threshold
            if len(candidate) <= self._config.max_chunk_size and (
                len(current) < self._config.min_chunk_size or related
            ):
                current = candidate
            else:
                groups.append(current)
                current = unit
        groups.append(current)
        return self._add_overlap(groups)

    def _speaker_groups(
        self, utterances: Sequence[_Utterance]
    ) -> List[Tuple[str, Dict[str, Any]]]:
        groups: List[List[_Utterance]] = []
        current = [utterances[0]]
        current_size = len(utterances[0].text)

        for utterance in utterances[1:]:
            current_text = " ".join(item.text for item in current)
            speaker_changed = utterance.speaker != current[-1].speaker
            similarity = self._similarity(current_text, utterance.text)
            if speaker_changed:
                similarity -= 0.1
            would_exceed = current_size + 1 + len(utterance.text) > self._config.max_chunk_size
            should_split = would_exceed or (
                current_size >= self._config.min_chunk_size
                and similarity < self._config.semantic_threshold
            )
            if should_split:
                groups.append(current)
                current = [utterance]
                current_size = len(utterance.text)
            else:
                current.append(utterance)
                current_size += 1 + len(utterance.text)
        groups.append(current)

        texts = [" ".join(item.text for item in group) for group in groups]
        overlapped = self._add_overlap(texts)
        result: List[Tuple[str, Dict[str, Any]]] = []
        for group, content in zip(groups, overlapped):
            speakers = list(dict.fromkeys(item.speaker for item in group))
            offsets = [item.time_offset for item in group if item.time_offset is not None]
            result.append(
                (
                    content,
                    {
                        "source": "speaker_aware_hybrid",
                        "has_speaker_info": True,
                        "speakers": speakers,
                        "speaker_name": speakers[0] if len(speakers) == 1 else None,
                        "time_offset": min(offsets) if offsets else None,
                        "last_time_offset": max(offsets) if offsets else None,
                        "semantic_threshold": self._config.semantic_threshold,
                    },
                )
            )
        return result

    async def chunk_document(
        self,
        text: str,
        doc_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Chunk]:
        if not text or not text.strip():
            return []

        utterances = self._parse_speaker_document(text)
        if utterances:
            grouped = self._speaker_groups(utterances)
        else:
            app_logger.info("[SpeakerAware] document=%s has no speaker marks; using local fallback", doc_id)
            grouped = [
                (
                    content,
                    {
                        "source": "local_semantic_fallback",
                        "has_speaker_info": False,
                        "semantic_threshold": self._config.semantic_threshold,
                    },
                )
                for content in self._group_plain_text(text)
            ]

        extra = metadata or {}
        return [
            Chunk(
                chunk_id=f"{doc_id}_{index}",
                content=content,
                metadata={"chars": len(content), **chunk_metadata, **extra},
            )
            for index, (content, chunk_metadata) in enumerate(grouped)
            if content.strip()
        ]
