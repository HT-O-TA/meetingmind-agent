"""训练意图分类头：bge-m3 整句向量 + 逻辑回归，只用开发集。

产物：app/services/assets/intent_head_v1.npz，包含 coef、intercept、classes，以及训练集与超参数的元数据。
C 取 tune_semantic_router.py 的 5 折交叉验证结果：C=4 时 cv_acc=0.837，C≥2 后进入平台期，取平台起点附近的值。

用法：
    python scripts/train_intent_head.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from scripts.tune_semantic_router import DEV_SETS, load_rows, embed  # noqa: E402

OUTPUT = BACKEND / "app/services/assets/intent_head_v1.npz"
C = 4.0


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    from sklearn.linear_model import LogisticRegression

    rows = load_rows()
    X = embed([r["question"] for r in rows])
    y = np.array([r["task_type"] for r in rows])
    clf = LogisticRegression(C=C, max_iter=2000, class_weight="balanced").fit(X, y)
    meta = {
        "trained_on": DEV_SETS,
        "dataset_sha256": {n: hashlib.sha256((BACKEND / "evaluation/datasets" / n).read_bytes()).hexdigest()[:16] for n in DEV_SETS},
        "rows": len(rows), "C": C, "encoder": "bge-m3 (normalize_embeddings=True)",
        "train_acc": round(float(clf.score(X, y)), 4),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    np.savez(OUTPUT, coef=clf.coef_.astype(np.float32), intercept=clf.intercept_.astype(np.float32),
             classes=np.array(clf.classes_), meta=np.array(json.dumps(meta, ensure_ascii=False)))
    print(json.dumps(meta, ensure_ascii=False))


if __name__ == "__main__":
    main()
