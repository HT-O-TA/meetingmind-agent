"""ASR 误差率：保留可审计归一化规则，不依赖外部评测包。"""
from __future__ import annotations

import re
import unicodedata

import jieba


def normalize_asr_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).lower()
    return "".join(
        char for char in normalized
        if not char.isspace() and not unicodedata.category(char).startswith(("P", "S"))
    )


def edit_distance(reference: list[str], hypothesis: list[str]) -> int:
    previous = list(range(len(hypothesis) + 1))
    for row, reference_token in enumerate(reference, start=1):
        current = [row]
        for column, hypothesis_token in enumerate(hypothesis, start=1):
            current.append(min(
                current[-1] + 1,
                previous[column] + 1,
                previous[column - 1] + (reference_token != hypothesis_token),
            ))
        previous = current
    return previous[-1]


def character_error_rate(reference: str, hypothesis: str) -> float:
    reference_chars = list(normalize_asr_text(reference))
    hypothesis_chars = list(normalize_asr_text(hypothesis))
    if not reference_chars:
        return 0.0 if not hypothesis_chars else 1.0
    return edit_distance(reference_chars, hypothesis_chars) / len(reference_chars)


def _words(text: str, language: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text).lower()
    normalized = re.sub(r"[^\w\u4e00-\u9fff]+", " ", normalized).strip()
    if language.startswith("zh"):
        return [token for token in jieba.lcut(normalized) if token.strip()]
    return normalized.split()


def word_error_rate(reference: str, hypothesis: str, language: str = "zh") -> float:
    reference_words = _words(reference, language)
    hypothesis_words = _words(hypothesis, language)
    if not reference_words:
        return 0.0 if not hypothesis_words else 1.0
    return edit_distance(reference_words, hypothesis_words) / len(reference_words)
