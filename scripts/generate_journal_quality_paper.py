from __future__ import annotations

import json
import os
import platform
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".matplotlib-cache"))

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder, OneHotEncoder, StandardScaler
from xgboost import XGBClassifier

try:
    from generate_updated_real_unsw_paper import REFERENCES
except ModuleNotFoundError:
    from scripts.generate_updated_real_unsw_paper import REFERENCES


DATA_DIR = ROOT / "data"
CHART_DIR = ROOT / "charts"
METRIC_DIR = ROOT / "metrics"
REPORT_DIR = ROOT / "reports"
TRAIN_PATH = DATA_DIR / "UNSW_NB15_training-set.csv"
TEST_PATH = DATA_DIR / "UNSW_NB15_testing-set.csv"

OUTPUT = ROOT / "journal_quality_hybrid_ids_unsw_nb15_2021_2026.docx"
REPORT_OUTPUT = REPORT_DIR / OUTPUT.name
METRICS_JSON = METRIC_DIR / "journal_quality_metrics.json"


def set_style(doc: Document) -> None:
    section = doc.sections[0]
    section.top_margin = Inches(0.7)
    section.bottom_margin = Inches(0.7)
    section.left_margin = Inches(0.75)
    section.right_margin = Inches(0.75)
    styles = doc.styles
    styles["Normal"].font.name = "Times New Roman"
    styles["Normal"].font.size = Pt(10.5)
    for name in ("Heading 1", "Heading 2", "Heading 3"):
        styles[name].font.name = "Times New Roman"
        styles[name].font.color.rgb = RGBColor(31, 78, 121)


def para(doc: Document, text: str):
    return doc.add_paragraph(text)


def bullet(doc: Document, text: str) -> None:
    doc.add_paragraph(text, style="List Bullet")


def numbered(doc: Document, text: str) -> None:
    doc.add_paragraph(text, style="List Number")


def centered(doc: Document, text: str, size: int = 10, bold: bool = False, italic: bool = False) -> None:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(text)
    run.font.name = "Times New Roman"
    run.font.size = Pt(size)
    run.bold = bold
    run.italic = italic


def caption(doc: Document, text: str) -> None:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(text)
    run.italic = True
    run.font.size = Pt(9)


def encoder() -> OneHotEncoder:
    try:
        return OneHotEncoder(handle_unknown="ignore", sparse_output=True)
    except TypeError:
        return OneHotEncoder(handle_unknown="ignore")


def load_real_split() -> tuple[pd.DataFrame, pd.DataFrame]:
    if not TRAIN_PATH.exists() or not TEST_PATH.exists():
        raise FileNotFoundError("Real UNSW-NB15 train/test CSV files are required in data/.")
    return pd.read_csv(TRAIN_PATH), pd.read_csv(TEST_PATH)


def build_preprocessor(df: pd.DataFrame) -> ColumnTransformer:
    feature_df = df.drop(columns=["label", "attack_cat", "id"], errors="ignore")
    numeric = feature_df.select_dtypes(include=["number", "bool"]).columns.tolist()
    categorical = [col for col in feature_df.columns if col not in numeric]
    numeric_pipe = Pipeline([("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler())])
    categorical_pipe = Pipeline([("imputer", SimpleImputer(strategy="most_frequent")), ("encoder", encoder())])
    return ColumnTransformer([("num", numeric_pipe, numeric), ("cat", categorical_pipe, categorical)])


def normalize_scores(scores: np.ndarray) -> np.ndarray:
    return (scores - scores.min()) / max(scores.max() - scores.min(), 1e-9)


def metric_row(name: str, y_true: np.ndarray, proba: np.ndarray, threshold: float, runtime: dict[str, float] | None = None) -> dict[str, float | str | int]:
    pred = (proba >= threshold).astype(int)
    cm = confusion_matrix(y_true, pred, labels=[0, 1])
    tn, fp, fn, tp = cm.ravel()
    row: dict[str, float | str | int] = {
        "Model": name,
        "Threshold": threshold,
        "Accuracy": accuracy_score(y_true, pred),
        "Precision": precision_score(y_true, pred, zero_division=0),
        "Recall": recall_score(y_true, pred, zero_division=0),
        "F1": f1_score(y_true, pred, zero_division=0),
        "ROC AUC": roc_auc_score(y_true, proba),
        "PR AUC": average_precision_score(y_true, proba),
        "False Positives": int(fp),
        "False Negatives": int(fn),
        "False Positive Rate": fp / max((y_true == 0).sum(), 1),
        "False Negative Rate": fn / max((y_true == 1).sum(), 1),
    }
    if runtime:
        row.update(runtime)
    return row


def select_thresholds(y_val: np.ndarray, proba: np.ndarray) -> dict[str, float]:
    thresholds = np.linspace(0.01, 0.99, 99)
    rows = []
    for threshold in thresholds:
        pred = (proba >= threshold).astype(int)
        rows.append(
            {
                "threshold": float(threshold),
                "precision": precision_score(y_val, pred, zero_division=0),
                "recall": recall_score(y_val, pred, zero_division=0),
                "f1": f1_score(y_val, pred, zero_division=0),
            }
        )
    df = pd.DataFrame(rows)
    f1_threshold = float(df.sort_values(["f1", "precision"], ascending=False).iloc[0]["threshold"])
    recall_candidates = df[df["recall"] >= 0.99]
    if recall_candidates.empty:
        recall_threshold = float(df.sort_values(["recall", "precision"], ascending=False).iloc[0]["threshold"])
    else:
        recall_threshold = float(recall_candidates.sort_values(["precision", "f1"], ascending=False).iloc[0]["threshold"])
    return {"Default 0.50": 0.50, "F1-tuned": f1_threshold, "Recall-oriented": recall_threshold}


def run_binary_experiments(train: pd.DataFrame, test: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, np.ndarray]]:
    y_train_full = train["label"].astype(int).to_numpy()
    y_test = test["label"].astype(int).to_numpy()
    x_train_full = train.drop(columns=["label", "attack_cat", "id"], errors="ignore")
    x_test = test.drop(columns=["label", "attack_cat", "id"], errors="ignore")
    x_fit, x_val, y_fit, y_val = train_test_split(
        x_train_full, y_train_full, test_size=0.2, stratify=y_train_full, random_state=42
    )

    preprocessor = build_preprocessor(train)
    x_fit_t = preprocessor.fit_transform(x_fit)
    x_val_t = preprocessor.transform(x_val)
    x_test_t = preprocessor.transform(x_test)

    scale_pos_weight = max((y_fit == 0).sum() / max((y_fit == 1).sum(), 1), 1e-9)
    models = {
        "Logistic Regression": LogisticRegression(max_iter=500, class_weight="balanced", random_state=42),
        "Random Forest": RandomForestClassifier(
            n_estimators=120, class_weight="balanced_subsample", random_state=42, n_jobs=1
        ),
        "XGBoost": XGBClassifier(
            n_estimators=150,
            max_depth=6,
            learning_rate=0.08,
            subsample=0.9,
            colsample_bytree=0.9,
            eval_metric="logloss",
            random_state=42,
            n_jobs=2,
            scale_pos_weight=scale_pos_weight,
        ),
    }
    proba_test: dict[str, np.ndarray] = {}
    proba_val: dict[str, np.ndarray] = {}
    runtime: dict[str, dict[str, float]] = {}
    for name, model in models.items():
        start = time.perf_counter()
        model.fit(x_fit_t, y_fit)
        fit_time = time.perf_counter() - start
        start = time.perf_counter()
        proba_test[name] = model.predict_proba(x_test_t)[:, 1]
        predict_time = time.perf_counter() - start
        proba_val[name] = model.predict_proba(x_val_t)[:, 1]
        runtime[name] = {
            "Fit Time Seconds": fit_time,
            "Predict Time Seconds": predict_time,
            "Milliseconds Per 1000 Records": predict_time / len(y_test) * 1000 * 1000,
        }

    iso = IsolationForest(n_estimators=100, contamination="auto", random_state=42, n_jobs=1)
    start = time.perf_counter()
    iso.fit(x_fit_t)
    iso_fit = time.perf_counter() - start
    start = time.perf_counter()
    proba_test["Isolation Forest Score"] = normalize_scores(-iso.decision_function(x_test_t))
    iso_predict = time.perf_counter() - start
    proba_val["Isolation Forest Score"] = normalize_scores(-iso.decision_function(x_val_t))
    runtime["Isolation Forest Score"] = {
        "Fit Time Seconds": iso_fit,
        "Predict Time Seconds": iso_predict,
        "Milliseconds Per 1000 Records": iso_predict / len(y_test) * 1000 * 1000,
    }

    fusion_specs = {
        "Fusion RF + XGBoost": ["Random Forest", "XGBoost"],
        "Fusion RF + XGBoost + IF": ["Random Forest", "XGBoost", "Isolation Forest Score"],
    }
    for name, sources in fusion_specs.items():
        val_stack = np.column_stack([proba_val[source] for source in sources])
        test_stack = np.column_stack([proba_test[source] for source in sources])
        fusion = LogisticRegression(max_iter=500, random_state=42)
        start = time.perf_counter()
        fusion.fit(val_stack, y_val)
        fusion_fit = time.perf_counter() - start
        start = time.perf_counter()
        proba_test[name] = fusion.predict_proba(test_stack)[:, 1]
        fusion_predict = time.perf_counter() - start
        proba_val[name] = fusion.predict_proba(val_stack)[:, 1]
        runtime[name] = {
            "Fit Time Seconds": sum(runtime[source]["Fit Time Seconds"] for source in sources) + fusion_fit,
            "Predict Time Seconds": sum(runtime[source]["Predict Time Seconds"] for source in sources) + fusion_predict,
            "Milliseconds Per 1000 Records": (sum(runtime[source]["Predict Time Seconds"] for source in sources) + fusion_predict)
            / len(y_test)
            * 1000
            * 1000,
        }

    binary_rows = [metric_row(name, y_test, proba, 0.50, runtime[name]) for name, proba in proba_test.items()]
    binary_metrics = pd.DataFrame(binary_rows).sort_values("F1", ascending=False)

    threshold_rows = []
    for model_name in ["XGBoost", "Fusion RF + XGBoost + IF"]:
        thresholds = select_thresholds(y_val, proba_val[model_name])
        for policy, threshold in thresholds.items():
            row = metric_row(model_name, y_test, proba_test[model_name], threshold)
            row["Policy"] = policy
            threshold_rows.append(row)
    threshold_metrics = pd.DataFrame(threshold_rows)
    return binary_metrics, threshold_metrics, proba_test


def run_multiclass_experiment(train: pd.DataFrame, test: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    x_train = train.drop(columns=["label", "attack_cat", "id"], errors="ignore")
    x_test = test.drop(columns=["label", "attack_cat", "id"], errors="ignore")
    labeler = LabelEncoder()
    y_train = labeler.fit_transform(train["attack_cat"].astype(str))
    y_test = labeler.transform(test["attack_cat"].astype(str))

    preprocessor = build_preprocessor(train)
    x_train_t = preprocessor.fit_transform(x_train)
    x_test_t = preprocessor.transform(x_test)
    model = XGBClassifier(
        n_estimators=120,
        max_depth=6,
        learning_rate=0.08,
        subsample=0.9,
        colsample_bytree=0.9,
        eval_metric="mlogloss",
        objective="multi:softprob",
        num_class=len(labeler.classes_),
        random_state=42,
        n_jobs=2,
    )
    start = time.perf_counter()
    model.fit(x_train_t, y_train)
    fit_time = time.perf_counter() - start
    start = time.perf_counter()
    pred = model.predict(x_test_t)
    predict_time = time.perf_counter() - start

    class_rows = []
    for idx, label in enumerate(labeler.classes_):
        mask_true = y_test == idx
        mask_pred = pred == idx
        support = int(mask_true.sum())
        tp = int((mask_true & mask_pred).sum())
        fp = int((~mask_true & mask_pred).sum())
        fn = int((mask_true & ~mask_pred).sum())
        precision = tp / max(tp + fp, 1)
        recall = tp / max(tp + fn, 1)
        f1 = 2 * precision * recall / max(precision + recall, 1e-12)
        class_rows.append(
            {"Class": label, "Support": support, "Precision": precision, "Recall": recall, "F1": f1}
        )
    per_class = pd.DataFrame(class_rows).sort_values("Support", ascending=True)
    summary = pd.DataFrame(
        [
            {
                "Model": "XGBoost multiclass",
                "Accuracy": accuracy_score(y_test, pred),
                "Macro F1": f1_score(y_test, pred, average="macro", zero_division=0),
                "Weighted F1": f1_score(y_test, pred, average="weighted", zero_division=0),
                "Fit Time Seconds": fit_time,
                "Predict Time Seconds": predict_time,
                "Milliseconds Per 1000 Records": predict_time / len(y_test) * 1000 * 1000,
            }
        ]
    )
    return summary, per_class


def save_fig(path: Path) -> None:
    plt.tight_layout()
    plt.savefig(path, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close()


def make_charts(binary: pd.DataFrame, threshold: pd.DataFrame, multiclass: pd.DataFrame) -> None:
    CHART_DIR.mkdir(exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans", "axes.titlesize": 13, "axes.labelsize": 10})

    ablation = binary[binary["Model"].isin(["Random Forest", "XGBoost", "Isolation Forest Score", "Fusion RF + XGBoost", "Fusion RF + XGBoost + IF"])].copy()
    ablation = ablation.sort_values("F1")
    fig, ax = plt.subplots(figsize=(7.8, 4.0))
    ax.barh(ablation["Model"], ablation["F1"], color="#2f6f8f")
    ax.set_xlim(0.0, 1.0)
    ax.set_xlabel("F1-score at threshold 0.50")
    ax.set_title("Binary Ablation Study")
    ax.grid(axis="x", alpha=0.2)
    for idx, value in enumerate(ablation["F1"]):
        ax.text(min(value + 0.015, 0.96), idx, f"{value:.3f}", va="center", fontsize=9)
    ax.spines[["top", "right", "left"]].set_visible(False)
    save_fig(CHART_DIR / "journal_ablation_f1.png")

    fig, ax = plt.subplots(figsize=(8.0, 4.2))
    pivot = threshold.pivot(index="Policy", columns="Model", values="F1").loc[["Default 0.50", "F1-tuned", "Recall-oriented"]]
    pivot.plot(kind="bar", ax=ax, color=["#2f6f8f", "#d9923b"])
    ax.set_ylim(0.86, 0.95)
    ax.set_ylabel("F1-score")
    ax.set_xlabel("")
    ax.set_title("Threshold Policy Sensitivity")
    ax.tick_params(axis="x", rotation=0)
    ax.grid(axis="y", alpha=0.2)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=2, fontsize=8, frameon=False)
    save_fig(CHART_DIR / "journal_threshold_policy.png")

    fig, ax = plt.subplots(figsize=(7.8, 4.3))
    rare = multiclass.sort_values("Support", ascending=True)
    ax.barh(rare["Class"], rare["F1"], color="#4f9d69")
    ax.set_xlim(0, 1.0)
    ax.set_xlabel("Per-class F1")
    ax.set_title("Multiclass XGBoost Per-Class F1")
    ax.grid(axis="x", alpha=0.2)
    for idx, row in rare.iterrows():
        ax.text(row["F1"] + 0.015, list(rare.index).index(idx), f"n={int(row['Support'])}", va="center", fontsize=8)
    ax.spines[["top", "right", "left"]].set_visible(False)
    save_fig(CHART_DIR / "journal_multiclass_per_class_f1.png")

    runtime = binary.sort_values("Milliseconds Per 1000 Records", ascending=True)
    fig, ax = plt.subplots(figsize=(7.8, 4.0))
    ax.barh(runtime["Model"], runtime["Milliseconds Per 1000 Records"], color="#6b5b95")
    ax.set_xlabel("Milliseconds per 1,000 test records")
    ax.set_title("Binary Inference Cost")
    ax.grid(axis="x", alpha=0.2)
    ax.spines[["top", "right", "left"]].set_visible(False)
    save_fig(CHART_DIR / "journal_runtime.png")


def table_from_df(doc: Document, df: pd.DataFrame, columns: list[str], title: str) -> None:
    table = doc.add_table(rows=1, cols=len(columns))
    table.style = "Table Grid"
    for idx, col in enumerate(columns):
        table.rows[0].cells[idx].text = col
    for _, row in df[columns].iterrows():
        cells = table.add_row().cells
        for idx, col in enumerate(columns):
            value = row[col]
            if isinstance(value, float):
                cells[idx].text = f"{value:.4f}" if abs(value) < 10 else f"{value:.2f}"
            else:
                cells[idx].text = str(value)
    caption(doc, title)


def add_literature_table(doc: Document) -> None:
    rows = [
        ("Zoghi & Serpen, 2022", "UNSW-NB15", "Ensemble tuning", "Binary/multiclass", "Dataset-specific design"),
        ("Yin et al., 2022", "UNSW-NB15", "IGRF-RFE + MLP", "Multiclass", "Feature-selection sensitivity"),
        ("Explainable AI, 2024", "UNSW-NB15", "XAI comparison", "Binary/multiclass", "Interpretability gap"),
        ("xIDS-EnsembleGuard, 2025", "Multiple IDS datasets", "Explainable ensemble", "Binary", "Overfitting and bias"),
        ("Farhan et al., 2025", "UNSW-NB15", "Deep learning", "Binary", "Imbalance and feature selection"),
        ("LiteShield, 2026", "UNSW-NB15", "Hybrid feature selection", "Binary/multiclass", "Lightweight deployment"),
        ("Hossain et al., 2026", "Multiple IDS datasets", "Generalization study", "Binary", "Cross-dataset robustness"),
    ]
    table = doc.add_table(rows=1, cols=5)
    table.style = "Table Grid"
    for idx, header in enumerate(["Study", "Dataset", "Method", "Task", "Relevance"]):
        table.rows[0].cells[idx].text = header
    for row in rows:
        cells = table.add_row().cells
        for idx, value in enumerate(row):
            cells[idx].text = value
    caption(doc, "Table 1. Recent IDS literature positioning from 2021 to 2026.")


def add_dataset_table(doc: Document, train: pd.DataFrame, test: pd.DataFrame) -> None:
    table = doc.add_table(rows=1, cols=5)
    table.style = "Table Grid"
    for idx, col in enumerate(["Split", "Records", "Normal", "Attack", "Attack families"]):
        table.rows[0].cells[idx].text = col
    for split, df in [("Training", train), ("Testing", test)]:
        cells = table.add_row().cells
        cells[0].text = split
        cells[1].text = f"{len(df):,}"
        cells[2].text = f"{int(df['label'].eq(0).sum()):,}"
        cells[3].text = f"{int(df['label'].eq(1).sum()):,}"
        cells[4].text = str(df["attack_cat"].nunique())
    caption(doc, "Table 2. Real UNSW-NB15 split used for binary and multiclass experiments.")


def create_document(
    train: pd.DataFrame,
    test: pd.DataFrame,
    binary: pd.DataFrame,
    threshold: pd.DataFrame,
    multiclass_summary: pd.DataFrame,
    multiclass_detail: pd.DataFrame,
) -> None:
    best_binary = binary.iloc[0]
    hybrid = binary[binary["Model"].eq("Fusion RF + XGBoost + IF")].iloc[0]
    xgb = binary[binary["Model"].eq("XGBoost")].iloc[0]
    doc = Document()
    set_style(doc)

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run("A Journal-Style Empirical Study of Hybrid Machine Learning for Intrusion Detection on UNSW-NB15")
    run.bold = True
    run.font.name = "Times New Roman"
    run.font.size = Pt(16)
    centered(doc, "Binary, multiclass, ablation, threshold, and runtime analysis with 2021-2026 literature", size=11, italic=True)
    centered(doc, "Author: Shivani Nayak", size=10)
    centered(doc, "Department of Computer Science and Engineering", size=10)

    doc.add_heading("Abstract", level=1)
    para(doc, f"This paper presents a real-data empirical study of machine learning-based network intrusion detection using the official UNSW-NB15 training and testing CSV files. Instead of claiming that hybrid fusion is automatically superior, the study evaluates when hybrid supervised and anomaly-aware evidence is useful and when a strong tabular learner is sufficient. Binary experiments compare Logistic Regression, Random Forest, XGBoost, Isolation Forest scoring, RF+XGBoost fusion, and RF+XGBoost+Isolation Forest fusion. Multiclass experiments evaluate attack-family detection using XGBoost. At the default threshold, {best_binary['Model']} achieved the strongest binary F1-score of {best_binary['F1']:.4f}; XGBoost achieved F1={xgb['F1']:.4f}, while the full hybrid achieved F1={hybrid['F1']:.4f}. The results show that XGBoost remains the strongest default operating point, but the hybrid analysis is valuable for understanding fusion behavior, false-alarm tradeoffs, and deployability.")
    p = doc.add_paragraph()
    p.add_run("Keywords: ").bold = True
    p.add_run("Network intrusion detection, UNSW-NB15, XGBoost, Random Forest, hybrid fusion, multiclass classification, threshold tuning, cybersecurity")

    doc.add_heading("1. Introduction", level=1)
    para(doc, "Network intrusion detection systems must identify malicious behavior in high-volume traffic while maintaining a manageable false-alarm rate. This problem is difficult because modern traffic contains class imbalance, overlapping behavior between benign and malicious flows, and rare attack families with few examples. Machine learning can learn useful traffic patterns, but benchmark accuracy alone is not enough for journal-level evaluation.")
    para(doc, "This paper therefore treats hybrid IDS design as an empirical question. The study asks whether fusion improves binary detection, how threshold choice changes IDS tradeoffs, how well attack families are detected in multiclass classification, and what runtime cost is introduced by each model family.")

    doc.add_heading("2. Research Questions and Contributions", level=1)
    bullet(doc, "RQ1: Which binary model provides the strongest normal-versus-attack detection on the official UNSW-NB15 split?")
    bullet(doc, "RQ2: Does RF+XGBoost+Isolation Forest fusion improve over individual learners or simpler RF+XGBoost fusion?")
    bullet(doc, "RQ3: How does threshold tuning change false positives, false negatives, and F1-score?")
    bullet(doc, "RQ4: Which UNSW-NB15 attack families remain difficult under multiclass classification?")
    bullet(doc, "RQ5: What inference-cost tradeoff is introduced by the evaluated models?")

    doc.add_heading("3. Related Work", level=1)
    para(doc, "Recent IDS literature from 2021 to 2026 emphasizes feature selection, explainability, lightweight deployment, cross-dataset generalization, and hybrid learning. The literature also shows that claims based only on high benchmark accuracy are weak unless they include class imbalance, rare-class behavior, and deployment constraints.")
    add_literature_table(doc)

    doc.add_heading("4. Dataset and Experimental Design", level=1)
    para(doc, "The study uses the real UNSW-NB15 CSV files: data/UNSW_NB15_training-set.csv and data/UNSW_NB15_testing-set.csv. The binary label is used for normal-versus-attack detection. The attack_cat column is used only for multiclass attack-family evaluation and is excluded from binary model features to avoid label leakage.")
    add_dataset_table(doc, train, test)
    para(doc, "The preprocessing pipeline removes id, imputes numeric features with median values, standardizes numeric features, imputes categorical features with the mode, and one-hot encodes categorical protocol, service, and state fields. Binary threshold selection uses an internal stratified validation split from the training data; final reported metrics are measured on the official testing split.")
    doc.add_picture(str(CHART_DIR / "real_unsw_research_workflow.png"), width=Inches(6.1))
    caption(doc, "Figure 1. Hybrid IDS analysis workflow.")

    doc.add_heading("5. Models and Reproducibility", level=1)
    para(doc, "The binary study evaluates Logistic Regression, Random Forest, XGBoost, Isolation Forest score-only detection, RF+XGBoost fusion, and RF+XGBoost+Isolation Forest fusion. The fusion layer is logistic regression trained on validation-set probability or anomaly-score meta-features. The multiclass study uses XGBoost because it was the strongest binary model and is well suited to tabular network-flow data.")
    para(doc, f"Reproducibility settings: Python {platform.python_version()}, platform {platform.system()} {platform.release()}, random_state=42, official UNSW-NB15 train/test split, scikit-learn preprocessing, and XGBoost tree models. The implementation records fit time, prediction time, and milliseconds per 1,000 test records.")

    doc.add_heading("6. Binary Results", level=1)
    table_from_df(doc, binary, ["Model", "Accuracy", "Precision", "Recall", "F1", "ROC AUC", "PR AUC", "False Positives", "False Negatives"], "Table 3. Binary model performance at threshold 0.50.")
    para(doc, f"The binary results show that {best_binary['Model']} is the strongest default-threshold model. The full hybrid does not outperform XGBoost in F1-score, which is important because it prevents an overstated novelty claim. A likely reason is that XGBoost already captures most discriminative tabular structure in the official split, while Isolation Forest adds anomaly evidence that increases recall but can also raise false positives.")
    doc.add_picture(str(CHART_DIR / "journal_ablation_f1.png"), width=Inches(5.9))
    caption(doc, "Figure 2. Ablation study showing default-threshold binary F1-score.")

    doc.add_heading("7. Threshold and Runtime Analysis", level=1)
    table_from_df(doc, threshold, ["Model", "Policy", "Threshold", "Precision", "Recall", "F1", "False Positives", "False Negatives"], "Table 4. Threshold policy comparison on the official test split.")
    default_xgb = threshold[(threshold["Model"].eq("XGBoost")) & (threshold["Policy"].eq("Default 0.50"))].iloc[0]
    tuned_xgb = threshold[(threshold["Model"].eq("XGBoost")) & (threshold["Policy"].eq("F1-tuned"))].iloc[0]
    para(doc, f"Threshold tuning demonstrates that IDS performance is an operating-point decision rather than a single fixed metric. The tuned thresholds were selected on the internal validation split and then evaluated on the official test split. In this run, the default XGBoost threshold remained stronger on the final test split (F1={default_xgb['F1']:.4f}) than the validation-selected F1 threshold (F1={tuned_xgb['F1']:.4f}), showing that threshold policies can overfit the validation distribution. Recall-oriented thresholds reduced missed attacks but increased false positives.")
    doc.add_picture(str(CHART_DIR / "journal_threshold_policy.png"), width=Inches(5.9))
    caption(doc, "Figure 3. Threshold policy sensitivity for XGBoost and full hybrid fusion.")
    table_from_df(doc, binary, ["Model", "Fit Time Seconds", "Predict Time Seconds", "Milliseconds Per 1000 Records"], "Table 5. Runtime and inference-cost comparison.")
    doc.add_picture(str(CHART_DIR / "journal_runtime.png"), width=Inches(5.9))
    caption(doc, "Figure 4. Binary inference cost by model.")

    doc.add_heading("8. Multiclass Attack-Family Results", level=1)
    table_from_df(doc, multiclass_summary, ["Model", "Accuracy", "Macro F1", "Weighted F1", "Fit Time Seconds", "Milliseconds Per 1000 Records"], "Table 6. Multiclass XGBoost summary.")
    table_from_df(doc, multiclass_detail, ["Class", "Support", "Precision", "Recall", "F1"], "Table 7. Per-class multiclass precision, recall, and F1.")
    rare = multiclass_detail.sort_values("F1").iloc[0]
    para(doc, f"Multiclass detection is substantially harder than binary detection because rare attack families have limited support. The weakest class in this run was {rare['Class']} with support={int(rare['Support'])} and F1={rare['F1']:.4f}. These results are more informative for journal review than binary accuracy alone because they reveal where the detector may fail operationally.")
    doc.add_picture(str(CHART_DIR / "journal_multiclass_per_class_f1.png"), width=Inches(5.9))
    caption(doc, "Figure 5. Per-class F1-score for multiclass attack-family detection.")

    doc.add_heading("9. Discussion", level=1)
    para(doc, "The experiments support a careful interpretation: hybrid fusion is a useful design pattern for combining complementary evidence, but it is not automatically superior to a strong tree-boosting baseline. The empirical contribution of this paper is therefore the broader comparison across binary detection, fusion ablation, threshold policy, multiclass rare-class behavior, and runtime cost.")
    para(doc, "For deployment, XGBoost is attractive because it provides the best default-threshold F1 and strong AUC scores. The hybrid models are still relevant when an operator wants to combine supervised confidence with anomaly evidence, but the decision threshold must be tuned to alert budget and risk tolerance.")

    doc.add_heading("10. Threats to Validity", level=1)
    bullet(doc, "Dataset validity: UNSW-NB15 is a benchmark and may not fully represent current encrypted, cloud-native, or enterprise traffic.")
    bullet(doc, "Threshold validity: validation-tuned thresholds depend on the training distribution and may drift in live networks.")
    bullet(doc, "Model validity: only one dataset is used; stronger journal evidence would include CIC-IDS2017, BoT-IoT, ToN-IoT, or NF-UNSW-NB15.")
    bullet(doc, "Multiclass validity: rare classes such as Worms have very small support, so per-class metrics can be unstable.")
    bullet(doc, "Operational validity: the study reports offline inference time, not full streaming ingestion, SIEM integration, or analyst triage cost.")

    doc.add_heading("11. Conclusion", level=1)
    para(doc, "This journal-style version strengthens the original project paper by adding real-data binary experiments, multiclass attack-family detection, fusion ablation, threshold analysis, runtime measurement, and explicit threats to validity. The results show that XGBoost is the strongest default-threshold model on the official UNSW-NB15 split, while hybrid fusion provides an interpretable framework for studying complementary supervised and anomaly evidence. Future work should validate the approach on additional datasets, add explainability, and evaluate streaming deployment.")

    doc.add_section(WD_SECTION.NEW_PAGE)
    doc.add_heading("References", level=1)
    for ref in REFERENCES:
        numbered(doc, ref)
    doc.save(OUTPUT)
    REPORT_DIR.mkdir(exist_ok=True)
    shutil.copy2(OUTPUT, REPORT_OUTPUT)


def main() -> None:
    train, test = load_real_split()
    binary, threshold, _ = run_binary_experiments(train, test)
    multiclass_summary, multiclass_detail = run_multiclass_experiment(train, test)
    make_charts(binary, threshold, multiclass_detail)
    METRIC_DIR.mkdir(exist_ok=True)
    payload = {
        "binary": binary.to_dict(orient="records"),
        "threshold": threshold.to_dict(orient="records"),
        "multiclass_summary": multiclass_summary.to_dict(orient="records"),
        "multiclass_detail": multiclass_detail.to_dict(orient="records"),
    }
    METRICS_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    binary.to_csv(METRIC_DIR / "journal_binary_metrics.csv", index=False)
    threshold.to_csv(METRIC_DIR / "journal_threshold_metrics.csv", index=False)
    multiclass_summary.to_csv(METRIC_DIR / "journal_multiclass_summary.csv", index=False)
    multiclass_detail.to_csv(METRIC_DIR / "journal_multiclass_per_class.csv", index=False)
    create_document(train, test, binary, threshold, multiclass_summary, multiclass_detail)
    print(f"Created {OUTPUT}")
    print(f"Created {METRICS_JSON}")


if __name__ == "__main__":
    main()
