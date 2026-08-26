"""兼容旧评估脚本；正式数据由运行时代码所有。"""

from app.data.rag_eval_dataset import RAG_EVAL_DATASET, get_eval_dataset, get_question_by_id


__all__ = ["RAG_EVAL_DATASET", "get_eval_dataset", "get_question_by_id"]
