"""Train the Stage B intent classifier.

    python -m ai_models.training.train_classifier

Pipeline: TF-IDF (word 1-2 grams) + scaled travel features →
LogisticRegression → CalibratedClassifierCV (sigmoid).

Metrics are written to ``ai_models/evaluation/metrics.json`` from a
template-disjoint holdout, so the reported numbers are honest.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from ai_models.training.corpus import INTENTS, build_dataset

ROOT = Path(__file__).resolve().parents[2]
MODEL_PATH = ROOT / "ai_models" / "saved_models" / "intent_pipeline.joblib"
METRICS_PATH = ROOT / "ai_models" / "evaluation" / "metrics.json"
NUMERIC = ["hours_to_checkin", "hours_to_lcd", "prior_count"]


def _frame(texts: list[str], seed: int = 3) -> pd.DataFrame:
    import random

    rng = random.Random(seed)
    return pd.DataFrame({
        "text": texts,
        "hours_to_checkin": [round(rng.uniform(-24, 240), 2) for _ in texts],
        "hours_to_lcd": [round(rng.uniform(-12, 168), 2) for _ in texts],
        "prior_count": [rng.choice([0, 0, 1, 2, 3]) for _ in texts],
    })


def build_pipeline() -> Pipeline:
    features = ColumnTransformer(
        transformers=[
            ("text", TfidfVectorizer(
                ngram_range=(1, 2), min_df=1, sublinear_tf=True, lowercase=True,
                strip_accents="unicode",
            ), "text"),
            ("numeric", StandardScaler(), NUMERIC),
        ],
        remainder="drop",
    )
    return Pipeline([
        ("features", features),
        ("clf", LogisticRegression(max_iter=2000, C=6.0, class_weight="balanced", random_state=7)),
    ])


def main() -> int:
    train_texts, train_labels = build_dataset(per_template=6, seed=7)
    holdout_texts, holdout_labels = build_dataset(per_template=4, seed=11, holdout=True)

    x_train = _frame(train_texts, seed=3)
    x_holdout = _frame(holdout_texts, seed=5)

    pipeline = build_pipeline()
    calibrated = CalibratedClassifierCV(pipeline, method="sigmoid", cv=3)
    calibrated.fit(x_train, train_labels)

    predicted = calibrated.predict(x_holdout)
    accuracy = float(accuracy_score(holdout_labels, predicted))
    macro_f1 = float(f1_score(holdout_labels, predicted, average="macro"))
    report = classification_report(holdout_labels, predicted, output_dict=True, zero_division=0)
    matrix = confusion_matrix(holdout_labels, predicted, labels=INTENTS).tolist()

    version = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "pipeline": calibrated,
            "classes": list(calibrated.classes_),
            "version": version,
            "numeric_medians": {
                "hours_to_checkin": float(x_train["hours_to_checkin"].median()),
                "hours_to_lcd": float(x_train["hours_to_lcd"].median()),
                "prior_count": float(x_train["prior_count"].median()),
            },
            "training": {
                "samples": int(len(train_texts)),
                "holdout_samples": int(len(holdout_texts)),
                "accuracy": round(accuracy, 4),
                "macro_f1": round(macro_f1, 4),
                "split": "template-disjoint holdout (no template appears in both sets)",
                "data": "SYNTHETIC — generated from per-intent templates, not real TBO tickets",
            },
        },
        MODEL_PATH,
    )

    METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
    METRICS_PATH.write_text(json.dumps({
        "generated_at": version,
        "model_path": str(MODEL_PATH.relative_to(ROOT)),
        "dataset": "SYNTHETIC (template-generated; no real TBO ticket text was used)",
        "train_samples": len(train_texts),
        "holdout_samples": len(holdout_texts),
        "holdout_accuracy": round(accuracy, 4),
        "holdout_macro_f1": round(macro_f1, 4),
        "split": "template-disjoint: every holdout template is unseen during training",
        "per_class": {
            intent: {
                "precision": round(report[intent]["precision"], 4),
                "recall": round(report[intent]["recall"], 4),
                "f1": round(report[intent]["f1-score"], 4),
                "support": int(report[intent]["support"]),
            }
            for intent in INTENTS if intent in report
        },
        "confusion_matrix": {"labels": INTENTS, "matrix": matrix},
    }, indent=2))

    print(f"trained on {len(train_texts)} synthetic samples")
    print(f"template-disjoint holdout: accuracy={accuracy:.4f} macro_f1={macro_f1:.4f} (n={len(holdout_texts)})")
    print(f"saved {MODEL_PATH}")
    print(f"metrics {METRICS_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
