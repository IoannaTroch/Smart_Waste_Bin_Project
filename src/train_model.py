#!/usr/bin/env python3
"""
train_model.py  —  train the ML virtual sensor (Milestone 9 / Lab 09).

Generates synthetic-but-realistic motion-count data (weekday lunch peaks, quiet
weekends), labels each hour busy/quiet, trains a RandomForest, and saves it to
models/busy_predictor.joblib for virtual_sensor_ml.py to load.

Run:  python train_model.py
"""

import os

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split


def generate_training_data(days: int = 30, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for day in range(days):
        dow = day % 7  # 0=Mon ... 6=Sun
        for hour in range(24):
            if dow in (5, 6):
                base = 2
            elif 8 <= hour <= 10:
                base = 15
            elif 11 <= hour <= 14:
                base = 25
            elif 15 <= hour <= 17:
                base = 12
            elif 18 <= hour <= 20:
                base = 8
            else:
                base = 1
            count = max(0, int(rng.normal(base, base * 0.3)))
            rows.append({
                "day_of_week": dow,
                "hour": hour,
                "is_weekend": 1 if dow in (5, 6) else 0,
                "event_count": count,
                "label": "busy" if count > 10 else "quiet",
            })
    return pd.DataFrame(rows)


def train_and_save(output_dir: str = None) -> RandomForestClassifier:
    if output_dir is None:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        output_dir = os.path.join(root, "models")
    os.makedirs(output_dir, exist_ok=True)

    df = generate_training_data()
    print(f"[train] {len(df)} samples | "
          f"busy={(df.label == 'busy').sum()} quiet={(df.label == 'quiet').sum()}")

    X = df[["day_of_week", "hour", "is_weekend"]]
    y = df["label"]
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=42)

    clf = RandomForestClassifier(n_estimators=50, random_state=42)
    clf.fit(X_tr, y_tr)

    print("\nModel evaluation:")
    print(classification_report(y_te, clf.predict(X_te)))

    path = os.path.join(output_dir, "busy_predictor.joblib")
    joblib.dump(clf, path)
    print(f"[train] Model saved -> {path}")
    return clf


if __name__ == "__main__":
    # Honor MODELS_DIR so the containerised one-shot `train` service writes the
    # model into the shared data volume that the ML virtual sensor reads from.
    train_and_save(os.getenv("MODELS_DIR"))
