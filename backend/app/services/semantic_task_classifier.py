"""语义任务类型识别：子句切分 + bge-m3 原型相似度。

关键词路由只认"待办/纪要/争议"等字面词，"分一下工""recap""没谈拢"这类同义
表达会落回 QA。本模块把问题按标点和顺承连接词切成子句，每个子句与各任务类型
的原型句做余弦相似度，取超过阈值且领先次优类足够多的类型；多个子句命中不同
业务类型即判为多任务。模型不可用时返回 None，调用方沿用关键词路由。
"""
from __future__ import annotations

import re
from pathlib import Path
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
    def __init__(self, encoder, *, threshold: float = 0.6, margin: float = 0.08, head=None):
        self._encoder = encoder
        self.threshold = threshold
        self.margin = margin
        # head = (coef[n_class, dim], intercept[n_class], classes[n_class])，由 load_intent_head() 提供
        self._head = head
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

    def classify_whole(self, vector) -> Optional[str]:
        """整句意图头（开发集训练的逻辑回归）；未加载时返回 None。返回 qa/todo/minutes/controversy/multi。"""
        if self._head is None:
            return None
        import numpy as np

        coef, intercept, classes = self._head
        return str(classes[int(np.argmax(np.asarray(vector) @ coef.T + intercept))])

    def detect(self, question: str) -> List[TaskType]:
        """返回识别到的任务类型（有序去重）；QA 只在多请求句式中作为独立子任务计入。"""
        clauses = self.split_clauses(question)
        vectors = self._encode([question] + clauses)
        head = self.classify_whole(vectors[0])
        if head is not None:
            return self._detect_with_head(head, vectors[1:])
        labels = self._classify(vectors)
        whole, per_clause = labels[0], labels[1:]
        business = [l for l in per_clause if l and l != TaskType.QA]
        if whole and whole != TaskType.QA:
            business.insert(0, whole)
        found = list(dict.fromkeys(business))
        if found and TaskType.QA in per_clause and _SEQUENCE_RE.search(question):
            found.append(TaskType.QA)
        return found

    def _detect_with_head(self, head: str, clause_vectors) -> List[TaskType]:
        """整句类型以意图头为准：qa 表示"不是业务任务"（压过关键词）；multi 时用子句原型补出具体类型。"""
        if head == "qa":
            return [TaskType.QA]
        if head != "multi":
            return [TaskType(head)]
        found = [l for l in self._classify(clause_vectors) if l and l != TaskType.QA]
        found = list(dict.fromkeys(found))
        return found if len(found) >= 2 else [TaskType.MULTI]


_instance: Optional[SemanticTaskClassifier] = None
_load_failed = False
INTENT_HEAD_PATH = Path(__file__).resolve().parent / "assets/intent_head_v1.npz"


def load_intent_head(path: Path = INTENT_HEAD_PATH):
    """加载开发集训练的整句意图头（scripts/train_intent_head.py 产出）；缺失时返回 None，回退原型规则。"""
    if not path.exists():
        return None
    import numpy as np

    data = np.load(path, allow_pickle=False)
    return data["coef"], data["intercept"], data["classes"]


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
        _instance = SemanticTaskClassifier(SentenceTransformer(path, local_files_only=True), head=load_intent_head())
    except Exception as exc:  # 依赖或模型缺失时保持关键词路由
        _load_failed = True
        app_logger.warning(f"[SemanticTask] 语义任务识别不可用，沿用关键词路由: {exc}")
    return _instance
