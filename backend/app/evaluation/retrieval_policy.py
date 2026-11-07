"""Bounded retrieval policies shared by runtime and offline experiments.

Policy files are operator-owned deployment configuration, never model output.
They change ranking only: authentication and ACL filtering stay with callers.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path


@dataclass(frozen=True)
class RetrievalPolicy:
    bm25_weight: float
    vector_weight: float

    def __post_init__(self):
        for value in (self.bm25_weight, self.vector_weight):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError("weights must be numeric")
            if not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError("weights must be finite and within [0, 1]")
        if not math.isclose(self.bm25_weight + self.vector_weight, 1.0):
            raise ValueError("weights must sum to one")

    @classmethod
    def parse(cls, value):
        if not isinstance(value, dict) or set(value) != {"bm25_weight", "vector_weight"}:
            raise ValueError("only retrieval weights may be optimized")
        return cls(**value)

    def to_dict(self):
        return asdict(self)


def load_policy(path: str) -> RetrievalPolicy:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != "meetingmind.retrieval-policy.v1":
        raise ValueError("unsupported deployment policy")
    if not payload.get("approved_by") or not payload.get("experiment_hash"):
        raise ValueError("policy requires approval and experiment provenance")
    return RetrievalPolicy.parse(payload["policy"])


def weighted_fusion(bm25_results, dense_results, policy: RetrievalPolicy):
    """Fuse already authorized candidates; preserve source IDs and text."""
    fused = {}
    for source, rows, weight in (
        ("bm25", bm25_results, policy.bm25_weight),
        ("dense", dense_results, policy.vector_weight),
    ):
        scores = [float(row.get("score", row.get("similarity", 0)) or 0) for row in rows]
        if any(not math.isfinite(score) for score in scores):
            raise ValueError("non-finite retrieval score")
        maximum = max(scores, default=0)
        seen = set()
        for row, raw in zip(rows, scores):
            key = row.get("chunk_id", row.get("doc_id", row.get("document_id")))
            if key is None or key in seen:
                raise ValueError("missing or duplicate chunk ID within retriever")
            seen.add(key)
            text = row.get("chunk_text", row.get("content", ""))
            contribution = max(0, raw) / maximum * weight if maximum > 0 else 0
            if key not in fused:
                fused[key] = dict(doc_id=key, chunk_id=key, document_id=row.get("document_id"),
                                  score=0.0, content=text, chunk_text=text, sources=[])
            item = fused[key]
            item["score"] += contribution
            item["sources"].append(source)
            if text:
                item["content"] = item["chunk_text"] = text
    return sorted(fused.values(), key=lambda item: (-item["score"], str(item["chunk_id"])))
