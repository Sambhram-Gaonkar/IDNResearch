from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from xgboost import XGBClassifier


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"


def load_unsw_nb15(data_dir: Path = DATA_DIR) -> pd.DataFrame:
    csv_files = sorted(data_dir.glob("*.csv"))
    if not csv_files:
        raise FileNotFoundError("Place UNSW-NB15 CSV files in the data/ directory.")
    return pd.concat((pd.read_csv(path) for path in csv_files), ignore_index=True)


def build_preprocessor(df: pd.DataFrame, target: str = "label") -> ColumnTransformer:
    feature_df = df.drop(columns=[target, "attack_cat"], errors="ignore")
    numeric_features = feature_df.select_dtypes(include=["number", "bool"]).columns.tolist()
    categorical_features = [col for col in feature_df.columns if col not in numeric_features]
    numeric_pipe = Pipeline([("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler())])
    categorical_pipe = Pipeline([
        ("imputer", SimpleImputer(strategy="most_frequent")),
        ("encoder", OneHotEncoder(handle_unknown="ignore")),
    ])
    return ColumnTransformer([
        ("num", numeric_pipe, numeric_features),
        ("cat", categorical_pipe, categorical_features),
    ])


def main() -> None:
    df = load_unsw_nb15()
    y = df["label"].astype(int)
    x = df.drop(columns=["label"], errors="ignore")
    preprocessor = build_preprocessor(df)
    x_train, x_test, y_train, y_test = train_test_split(x, y, test_size=0.25, stratify=y, random_state=42)
    x_train_t = preprocessor.fit_transform(x_train)
    x_test_t = preprocessor.transform(x_test)

    models = {
        "Logistic Regression": LogisticRegression(max_iter=1000, random_state=42),
        "Random Forest": RandomForestClassifier(n_estimators=200, random_state=42, n_jobs=1),
        "XGBoost": XGBClassifier(eval_metric="logloss", random_state=42, n_jobs=2),
    }

    probabilities = {}
    for name, model in models.items():
        model.fit(x_train_t, y_train)
        probabilities[name] = model.predict_proba(x_test_t)[:, 1]

    iso = IsolationForest(n_estimators=150, contamination="auto", random_state=42)
    iso.fit(x_train_t)
    iso_test = -iso.decision_function(x_test_t)
    iso_train = -iso.decision_function(x_train_t)
    iso_test = (iso_test - iso_test.min()) / max(iso_test.max() - iso_test.min(), 1e-9)
    iso_train = (iso_train - iso_train.min()) / max(iso_train.max() - iso_train.min(), 1e-9)

    stacked_train = np.column_stack([
        models["Random Forest"].predict_proba(x_train_t)[:, 1],
        models["XGBoost"].predict_proba(x_train_t)[:, 1],
        iso_train,
    ])
    stacked_test = np.column_stack([probabilities["Random Forest"], probabilities["XGBoost"], iso_test])
    fusion = LogisticRegression(max_iter=1000, random_state=42)
    fusion.fit(stacked_train, y_train)
    probabilities["Hybrid RF + XGBoost + Isolation Forest"] = fusion.predict_proba(stacked_test)[:, 1]

    rows = []
    for name, proba in probabilities.items():
        pred = (proba >= 0.5).astype(int)
        rows.append({
            "Model": name,
            "Accuracy": accuracy_score(y_test, pred),
            "Precision": precision_score(y_test, pred, zero_division=0),
            "Recall": recall_score(y_test, pred, zero_division=0),
            "F1": f1_score(y_test, pred, zero_division=0),
            "ROC AUC": roc_auc_score(y_test, proba),
        })
    print(pd.DataFrame(rows).sort_values("F1", ascending=False).to_string(index=False))


if __name__ == "__main__":
    main()
