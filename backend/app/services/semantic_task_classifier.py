"""语义任务类型识别：子句切分 + bge-m3 原型相似度。

关键词路由只认"待办/纪要/争议"等字面词，"分一下工""recap""没谈拢"这类同义
表达会落回 QA。本模块把问题按标点和顺承连接词切成子句，每个子句与各任务类型
的原型句做余弦相似度，取超过阈值且领先次优类足够多的类型；多个子句命中不同
业务类型即判为多任务。模型不可用时返回 None，调用方沿用关键词路由。
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

from app.agents.state import TaskType
from app.core.logger import app_logger

# 原型句只描述"用户想要什么"，不追求覆盖所有说法；阈值在 route_eval 开发集上标定。
PROTOTYPES: Dict[TaskType, List[str]] = {
    TaskType.TODO: [
        "列出会议的待办事项", "提取行动项和负责人", "每个人会后要做什么",
        "整理任务分工和截止时间", "下一步工作安排", "把布置的任务做成清单",
        "list the action items", "what are the next steps", "谁负责跟进哪些事情，全部列出来",
    ],
    TaskType.MINUTES: [
        "生成会议纪要", "总结整场会议", "写一份会议摘要", "概括这次会议讲了什么",
        "整理会议记录", "给没参会的人讲讲会议的主要内容", "recap the meeting",
        "meeting summary", "把整个会浓缩成几段话",
    ],
    TaskType.CONTROVERSY: [
        "会议中有哪些争议点", "大家在哪些问题上有分歧", "哪些地方没有达成一致",
        "谁和谁意见不同", "有哪些反对意见", "哪里没谈拢", "any disagreements in the meeting",
        "找出意见冲突的地方",
    ],
    TaskType.QA: [
        "会上谁负责这个模块", "预算最后定了多少", "为什么决定推迟", "某个人对方案是什么态度",
        "这个话题讨论了什么", "上线日期是哪天", "他提到的数据是多少", "会议的结论是什么",
        "张三的观点是什么", "what did they say about pricing",
    ],
}

_SPLIT_RE = re.compile(r"[，,。；;！!？?、\n：:]|(?:然后|另外|顺便|并且|再把|再出|再给|再列|还有|同时|以及|and then|also|plus)")
_SEQUENCE_RE = re.compile(r"先.+(再|然后)|另外|顺便|and then|also|plus|；|;")


class SemanticTaskClassifier:
    # 阈值在 route_eval_v1 + heldout_v1（107 条开发集）上网格标定：margin=0.08 时
    # threshold 0.55~0.65 准确率同为 0.972，取中值；最终泛化以 test_v2 为准。
    def __init__(self, encoder, *, threshold: float = 0.6, margin: float = 0.08):
        self._encoder = encoder
        self.threshold = threshold
        self.margin = margin
        self._labels: List[TaskType] = []
        texts: List[str] = []
        for label, examples in PROTOTYPES.items():
            self._labels.extend([label] * len(examples))
            texts.extend(examples)
        self._proto = self._encode(texts)

    def _encode(self, texts: List[str]):
        return self._encoder.encode(texts, normalize_embeddings=True, show_progress_bar=False)

    @staticmethod
    def split_clauses(question: str) -> List[str]:
        parts = [p.strip() for p in _SPLIT_RE.split(question or "") if p and p.strip()]
        return [p for p in parts if len(p) >= 2] or [question.strip()]

    def _classify(self, vectors) -> List[Optional[TaskType]]:
        import numpy as np

        sims = np.asarray(vectors) @ np.asarray(self._proto).T
        results: List[Optional[TaskType]] = []
        for row in sims:
            best_by_label: Dict[TaskType, float] = {}
            for label, score in zip(self._labels, row):
                best_by_label[label] = max(best_by_label.get(label, -1.0), float(score))
            ranked = sorted(best_by_label.items(), key=lambda x: -x[1])
            (top, top_score), (_, second) = ranked[0], ranked[1]
            ok = top_score >= self.threshold and top_score - second >= self.margin
            results.append(top if ok else None)
        return results

    def detect(self, question: str) -> List[TaskType]:
        """返回识别到的任务类型（有序去重）；QA 只在多请求句式中作为独立子任务计入。"""
        clauses = self.split_clauses(question)
        labels = self._classify(self._encode([question] + clauses))
        whole, per_clause = labels[0], labels[1:]
        business = [l for l in per_clause if l and l != TaskType.QA]
        if whole and whole != TaskType.QA:
            business.insert(0, whole)
        found = list(dict.fromkeys(business))
        if found and TaskType.QA in per_clause and _SEQUENCE_RE.search(question):
            found.append(TaskType.QA)
        return found


_instance: Optional[SemanticTaskClassifier] = None
_load_failed = False


def get_semantic_task_classifier() -> Optional[SemanticTaskClassifier]:
    """按需加载本地 bge-m3；不可用时返回 None 并只告警一次。"""
    global _instance, _load_failed
    if _instance is not None or _load_failed:
        return _instance
    try:
        import os
        from app.core.config import settings
        from sentence_transformers import SentenceTransformer

        path = settings.LOCAL_EMBEDDING_MODEL_PATH
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        _instance = SemanticTaskClassifier(SentenceTransformer(path, local_files_only=True))
    except Exception as exc:  # 依赖或模型缺失时保持关键词路由
        _load_failed = True
        app_logger.warning(f"[SemanticTask] 语义任务识别不可用，沿用关键词路由: {exc}")
    return _instance
