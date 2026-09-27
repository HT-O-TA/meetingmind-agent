"""在开发集上离线调参语义路由（缓存 bge-m3 向量，不加载完整路由）。

只允许使用开发集：route_eval_v1、route_eval_heldout_v1、route_eval_dev_v2。
test_v3 已看过失败样本、test_v4 为盲测集，二者都不得出现在这里。

用法：
    python scripts/tune_semantic_router.py --cv 5
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
DEV_SETS = ["route_eval_v1.jsonl", "route_eval_heldout_v1.jsonl", "route_eval_dev_v2.jsonl"]
FORBIDDEN = {"route_eval_test_v2.jsonl", "route_eval_test_v3.jsonl", "route_eval_test_v4.jsonl"}
CACHE = BACKEND / "data/_dev_embed_cache.npz"  # backend/data/ 已被 gitignore


def load_rows():
    rows = []
    for name in DEV_SETS:
        assert name not in FORBIDDEN
        for line in (BACKEND / "evaluation/datasets" / name).read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                row["_set"] = name
                rows.append(row)
    return rows


def embed(texts):
    from app.core.config import settings
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(settings.LOCAL_EMBEDDING_MODEL_PATH, local_files_only=True)
    return model.encode(texts, normalize_embeddings=True, show_progress_bar=False, batch_size=32)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--cv", type=int, default=5)
    args = parser.parse_args()
    rows = load_rows()
    questions = [r["question"] for r in rows]
    if CACHE.exists() and list(np.load(CACHE, allow_pickle=True)["q"]) == questions:
        X = np.load(CACHE, allow_pickle=True)["x"]
    else:
        X = embed(questions)
        np.savez(CACHE, q=np.array(questions, dtype=object), x=X)
    y = np.array([r["task_type"] for r in rows])

    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedKFold, cross_val_predict

    print(f"dev rows={len(rows)} labels={dict(zip(*np.unique(y, return_counts=True)))}")
    for C in (0.5, 1, 2, 4, 8, 16):
        clf = LogisticRegression(C=C, max_iter=2000, class_weight="balanced")
        pred = cross_val_predict(clf, X, y, cv=StratifiedKFold(args.cv, shuffle=True, random_state=0))
        acc = float((pred == y).mean())
        dev2 = np.array([r["_set"] == "route_eval_dev_v2.jsonl" for r in rows])
        print(f"C={C:<4} cv_acc={acc:.3f} dev_v2_cv_acc={(pred[dev2] == y[dev2]).mean():.3f}")


if __name__ == "__main__":
    main()
