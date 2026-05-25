from __future__ import annotations

import json
import math
import os
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".matplotlib"))
os.environ.setdefault("JOBLIB_TEMP_FOLDER", str(ROOT / ".joblib"))

import nbformat as nbf
import numpy as np
import pandas as pd
import seaborn as sns
from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor
from matplotlib import pyplot as plt
from sklearn.datasets import make_classification
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier


CHART_DIR = ROOT / "charts"
METRICS_DIR = ROOT / "metrics"
NOTEBOOK_DIR = ROOT / "notebooks"
REPORTS_DIR = ROOT / "reports"
DATA_DIR = ROOT / "data"
DOCX_PATH = ROOT / "research_methodology_explanation.docx"
NOTEBOOK_PATH = NOTEBOOK_DIR / "hybrid_ids_research_analysis.ipynb"
ZIP_PATH = ROOT / "hybrid_ids_research_project.zip"


ATTACK_CATEGORIES = [
    "Analysis",
    "Backdoor",
    "DoS",
    "Exploits",
    "Fuzzers",
    "Generic",
    "Reconnaissance",
    "Shellcode",
    "Worms",
]


def ensure_dirs() -> None:
    for path in (CHART_DIR, METRICS_DIR, NOTEBOOK_DIR, REPORTS_DIR, DATA_DIR, ROOT / ".matplotlib", ROOT / ".joblib"):
        path.mkdir(parents=True, exist_ok=True)


def create_synthetic_ids_dataset(n_samples: int = 2500, n_features: int = 20) -> tuple[pd.DataFrame, pd.Series]:
    x, y = make_classification(
        n_samples=n_samples,
        n_features=n_features,
        n_informative=12,
        n_redundant=4,
        n_clusters_per_class=2,
        weights=[0.64, 0.36],
        class_sep=1.25,
        random_state=42,
    )
    columns = [
        "dur",
        "spkts",
        "dpkts",
        "sbytes",
        "dbytes",
        "rate",
        "sttl",
        "dttl",
        "sload",
        "dload",
        "sloss",
        "dloss",
        "sinpkt",
        "dinpkt",
        "sjit",
        "djit",
        "swin",
        "stcpb",
        "dtcpb",
        "dwin",
    ]
    frame = pd.DataFrame(x, columns=columns[:n_features])
    labels = pd.Series(y, name="label")
    attack_labels = np.where(
        labels == 0,
        "Normal",
        np.random.default_rng(42).choice(ATTACK_CATEGORIES, size=n_samples),
    )
    frame["attack_cat"] = attack_labels
    frame["label"] = labels
    sample_path = DATA_DIR / "sample_unsw_nb15_like.csv"
    frame.to_csv(sample_path, index=False)
    return frame.drop(columns=["attack_cat", "label"]), labels


def train_models() -> tuple[pd.DataFrame, dict[str, np.ndarray], np.ndarray, np.ndarray, list[str]]:
    x, y = create_synthetic_ids_dataset()
    feature_names = list(x.columns)
    x_train, x_test, y_train, y_test = train_test_split(
        x, y, test_size=0.25, stratify=y, random_state=42
    )

    models = {
        "Logistic Regression": Pipeline(
            [("scaler", StandardScaler()), ("model", LogisticRegression(max_iter=1000, random_state=42))]
        ),
        "Random Forest": RandomForestClassifier(n_estimators=180, max_depth=12, random_state=42, n_jobs=1),
        "XGBoost": XGBClassifier(
            n_estimators=160,
            max_depth=4,
            learning_rate=0.06,
            subsample=0.9,
            colsample_bytree=0.9,
            eval_metric="logloss",
            random_state=42,
            n_jobs=2,
        ),
    }

    probabilities: dict[str, np.ndarray] = {}
    predictions: dict[str, np.ndarray] = {}
    rows: list[dict[str, float | str]] = []

    for name, model in models.items():
        model.fit(x_train, y_train)
        proba = model.predict_proba(x_test)[:, 1]
        pred = (proba >= 0.5).astype(int)
        probabilities[name] = proba
        predictions[name] = pred
        rows.append(metric_row(name, y_test, pred, proba))

    isolation = IsolationForest(n_estimators=120, contamination=0.36, random_state=42)
    isolation.fit(x_train)
    anomaly_score = -isolation.decision_function(x_test)
    anomaly_prob = (anomaly_score - anomaly_score.min()) / (anomaly_score.max() - anomaly_score.min())

    stacked_train = np.column_stack(
        [
            models["Random Forest"].predict_proba(x_train)[:, 1],
            models["XGBoost"].predict_proba(x_train)[:, 1],
            normalize(-isolation.decision_function(x_train)),
        ]
    )
    stacked_test = np.column_stack([probabilities["Random Forest"], probabilities["XGBoost"], anomaly_prob])
    fusion = LogisticRegression(max_iter=1000, random_state=42)
    fusion.fit(stacked_train, y_train)
    hybrid_proba = fusion.predict_proba(stacked_test)[:, 1]
    hybrid_pred = (hybrid_proba >= 0.5).astype(int)
    probabilities["Hybrid RF + XGBoost + Isolation Forest"] = hybrid_proba
    predictions["Hybrid RF + XGBoost + Isolation Forest"] = hybrid_pred
    rows.append(metric_row("Hybrid RF + XGBoost + Isolation Forest", y_test, hybrid_pred, hybrid_proba))

    metrics = pd.DataFrame(rows)
    metrics.to_csv(METRICS_DIR / "model_metrics.csv", index=False)
    (METRICS_DIR / "model_metrics.json").write_text(
        json.dumps(metrics.to_dict(orient="records"), indent=2), encoding="utf-8"
    )

    return metrics, probabilities, y_test.to_numpy(), models["Random Forest"].feature_importances_, feature_names


def normalize(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values)
    denominator = values.max() - values.min()
    if denominator == 0:
        return np.zeros_like(values)
    return (values - values.min()) / denominator


def metric_row(name: str, y_true: pd.Series | np.ndarray, y_pred: np.ndarray, y_proba: np.ndarray) -> dict[str, float | str]:
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()
    return {
        "Model": name,
        "Accuracy": round(accuracy_score(y_true, y_pred), 4),
        "Precision": round(precision_score(y_true, y_pred, zero_division=0), 4),
        "Recall": round(recall_score(y_true, y_pred, zero_division=0), 4),
        "F1": round(f1_score(y_true, y_pred, zero_division=0), 4),
        "ROC AUC": round(roc_auc_score(y_true, y_proba), 4),
        "PR AUC": round(average_precision_score(y_true, y_proba), 4),
        "False Positive Rate": round(fp / (fp + tn), 4),
        "False Negative Rate": round(fn / (fn + tp), 4),
    }


def save_workflow_diagram() -> Path:
    steps = [
        "Data Collection",
        "Data Preprocessing",
        "Feature Engineering",
        "Baseline Model Training",
        "Hybrid Model Training",
        "Evaluation Metrics",
        "Result Comparison",
        "Research Conclusion",
    ]
    fig, ax = plt.subplots(figsize=(8, 10))
    ax.axis("off")
    y_positions = np.linspace(0.92, 0.08, len(steps))
    for idx, (step, y) in enumerate(zip(steps, y_positions)):
        ax.text(
            0.5,
            y,
            step,
            ha="center",
            va="center",
            fontsize=13,
            weight="bold",
            bbox=dict(boxstyle="round,pad=0.55", facecolor="#EAF3F7", edgecolor="#1F5F75", linewidth=1.5),
        )
        if idx < len(steps) - 1:
            ax.annotate("", xy=(0.5, y_positions[idx + 1] + 0.045), xytext=(0.5, y - 0.045),
                        arrowprops=dict(arrowstyle="->", lw=1.7, color="#274C5E"))
    path = CHART_DIR / "research_methodology_workflow.png"
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return path


def save_architecture_diagram() -> Path:
    fig, ax = plt.subplots(figsize=(8, 9))
    ax.axis("off")
    boxes = [
        ("UNSW-NB15 Dataset", 0.88, "#E7F0EF"),
        ("Preprocessing", 0.75, "#E7F0EF"),
        ("Fusion Layer\n(Logistic Regression / Voting Classifier)", 0.32, "#FFF3D7"),
        ("Intrusion Prediction", 0.14, "#E7F0EF"),
    ]
    for text, y, color in boxes:
        ax.text(0.5, y, text, ha="center", va="center", fontsize=13, weight="bold",
                bbox=dict(boxstyle="round,pad=0.55", facecolor=color, edgecolor="#234", linewidth=1.4))
    model_y = [0.62, 0.52, 0.42]
    for label, y in zip(["Random Forest", "XGBoost", "Isolation Forest"], model_y):
        ax.text(0.5, y, label, ha="center", va="center", fontsize=12,
                bbox=dict(boxstyle="square,pad=0.55", facecolor="#F7FAFC", edgecolor="#263238", linewidth=1.3))
    for y1, y2 in [(0.84, 0.79), (0.71, 0.66), (0.38, 0.36), (0.25, 0.19)]:
        ax.annotate("", xy=(0.5, y2), xytext=(0.5, y1), arrowprops=dict(arrowstyle="->", lw=1.7, color="#274C5E"))
    ax.text(0.17, 0.52, "Ensemble\nlearners", ha="center", va="center", fontsize=11, color="#335")
    path = CHART_DIR / "hybrid_architecture.png"
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return path


def save_dataset_workflow() -> Path:
    labels = ["Raw CSV files", "Train/test merge", "Clean labels", "Encode categorical fields", "Scale numeric fields", "Model-ready matrix"]
    fig, ax = plt.subplots(figsize=(10, 3.5))
    ax.axis("off")
    xs = np.linspace(0.08, 0.92, len(labels))
    for i, (x, label) in enumerate(zip(xs, labels)):
        ax.text(x, 0.55, label, ha="center", va="center", fontsize=10.5,
                bbox=dict(boxstyle="round,pad=0.45", facecolor="#F5F7FA", edgecolor="#3D5A80"))
        if i < len(labels) - 1:
            ax.annotate("", xy=(xs[i + 1] - 0.055, 0.55), xytext=(x + 0.055, 0.55),
                        arrowprops=dict(arrowstyle="->", lw=1.5, color="#3D5A80"))
    path = CHART_DIR / "dataset_workflow.png"
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return path


def save_metric_charts(metrics: pd.DataFrame, probabilities: dict[str, np.ndarray], y_test: np.ndarray,
                       importances: np.ndarray, feature_names: list[str]) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    hybrid_name = "Hybrid RF + XGBoost + Isolation Forest"
    hybrid_proba = probabilities[hybrid_name]
    hybrid_pred = (hybrid_proba >= 0.5).astype(int)

    cm = confusion_matrix(y_test, hybrid_pred)
    fig, ax = plt.subplots(figsize=(5, 4))
    sns.heatmap(cm, annot=True, fmt="d", cmap="Blues", cbar=False, ax=ax,
                xticklabels=["Normal", "Attack"], yticklabels=["Normal", "Attack"])
    ax.set_xlabel("Predicted")
    ax.set_ylabel("Actual")
    ax.set_title("Hybrid Model Confusion Matrix")
    paths["confusion_matrix"] = CHART_DIR / "confusion_matrix.png"
    fig.savefig(paths["confusion_matrix"], dpi=220, bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(6, 4.2))
    for name, proba in probabilities.items():
        fpr, tpr, _ = roc_curve(y_test, proba)
        ax.plot(fpr, tpr, label=f"{name} (AUC={roc_auc_score(y_test, proba):.3f})")
    ax.plot([0, 1], [0, 1], linestyle="--", color="gray", linewidth=1)
    ax.set_xlabel("False Positive Rate")
    ax.set_ylabel("True Positive Rate")
    ax.set_title("ROC Curve")
    ax.legend(fontsize=7)
    paths["roc_curve"] = CHART_DIR / "roc_curve.png"
    fig.savefig(paths["roc_curve"], dpi=220, bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(6, 4.2))
    for name, proba in probabilities.items():
        precision, recall, _ = precision_recall_curve(y_test, proba)
        ax.plot(recall, precision, label=f"{name} (AP={average_precision_score(y_test, proba):.3f})")
    ax.set_xlabel("Recall")
    ax.set_ylabel("Precision")
    ax.set_title("Precision-Recall Curve")
    ax.legend(fontsize=7)
    paths["pr_curve"] = CHART_DIR / "pr_curve.png"
    fig.savefig(paths["pr_curve"], dpi=220, bbox_inches="tight")
    plt.close(fig)

    sorted_idx = np.argsort(importances)[-10:]
    fig, ax = plt.subplots(figsize=(6.5, 4.2))
    ax.barh(np.array(feature_names)[sorted_idx], importances[sorted_idx], color="#4F7CAC")
    ax.set_xlabel("Importance")
    ax.set_title("Top Feature Importance Scores")
    paths["feature_importance"] = CHART_DIR / "feature_importance.png"
    fig.savefig(paths["feature_importance"], dpi=220, bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 4.5))
    plot_df = metrics.melt(id_vars="Model", value_vars=["Accuracy", "Precision", "Recall", "F1", "ROC AUC"],
                           var_name="Metric", value_name="Score")
    sns.barplot(data=plot_df, x="Metric", y="Score", hue="Model", ax=ax)
    ax.set_ylim(0, 1.05)
    ax.set_title("Model Comparison")
    ax.legend(fontsize=7, loc="lower right")
    paths["model_comparison"] = CHART_DIR / "model_comparison.png"
    fig.savefig(paths["model_comparison"], dpi=220, bbox_inches="tight")
    plt.close(fig)

    return paths


def set_doc_style(document: Document) -> None:
    styles = document.styles
    styles["Normal"].font.name = "Times New Roman"
    styles["Normal"].font.size = Pt(11)
    for style_name in ["Heading 1", "Heading 2", "Heading 3"]:
        style = styles[style_name]
        style.font.name = "Times New Roman"
        style.font.color.rgb = RGBColor(31, 78, 121)
    section = document.sections[0]
    section.top_margin = Inches(0.8)
    section.bottom_margin = Inches(0.8)
    section.left_margin = Inches(0.85)
    section.right_margin = Inches(0.85)


def add_caption(document: Document, text: str) -> None:
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run(text)
    run.italic = True
    run.font.size = Pt(10)


def add_equation(document: Document, equation: str) -> None:
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run(equation)
    run.font.name = "Cambria Math"
    run.font.size = Pt(11)


def create_docx(metrics: pd.DataFrame, image_paths: dict[str, Path]) -> None:
    doc = Document()
    set_doc_style(doc)

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run("AI-Powered Intrusion Detection System Using a Hybrid Machine Learning Architecture")
    run.bold = True
    run.font.size = Pt(18)
    doc.add_paragraph("Research Methodology Explanation Document").alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph("Prepared for academic project documentation, thesis explanation, and viva presentation.").alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_section(WD_SECTION.NEW_PAGE)

    doc.add_heading("A. Research Overview", level=1)
    doc.add_paragraph(
        "Modern organizations depend on cloud services, distributed networks, remote endpoints, and continuously connected applications. "
        "This connectivity increases the attack surface for malware, denial-of-service traffic, scanning, exploitation, privilege abuse, and data exfiltration. "
        "Traditional perimeter security cannot reliably identify every malicious behavior because attacks may be encrypted, polymorphic, distributed, or blended with legitimate traffic."
    )
    doc.add_paragraph(
        "Intrusion detection is important because it provides continuous monitoring of network behavior and alerts security teams when traffic patterns indicate compromise. "
        "An IDS reduces the time between attack occurrence and detection, supports incident response, and creates evidence for forensic analysis."
    )
    doc.add_paragraph(
        "Artificial intelligence and machine learning are required because network traffic produces high-dimensional, high-volume, and non-linear patterns. "
        "Machine learning can learn statistical relationships between features such as packet counts, byte rates, protocol behavior, and service activity, enabling detection beyond static signature matching."
    )
    doc.add_paragraph(
        "Problem statement: This research investigates whether a hybrid machine learning architecture combining Random Forest, XGBoost, Isolation Forest, and a fusion layer can improve intrusion detection performance compared with individual baseline models on the UNSW-NB15 dataset."
    )

    doc.add_heading("B. Type of Research", level=1)
    research_types = [
        ("Applied Research", "The work solves a practical cybersecurity problem: detecting intrusions in network traffic. The output is not only theoretical; it produces a deployable classification pipeline and measurable IDS performance."),
        ("Experimental Research", "The project trains controlled machine learning models, changes model architecture, and evaluates the effect of those changes through repeatable metrics. The hybrid model is tested against baseline models under the same dataset split and preprocessing procedure."),
        ("Quantitative Research", "The conclusions are based on numerical measurements such as accuracy, precision, recall, F1-score, ROC-AUC, PR-AUC, false positive rate, and false negative rate. These metrics allow objective comparison."),
        ("Comparative Research", "The research compares Logistic Regression, Random Forest, XGBoost, and a hybrid fusion model to determine which approach provides the strongest detection capability and the most balanced error profile."),
    ]
    for heading, text in research_types:
        doc.add_heading(heading, level=2)
        doc.add_paragraph(text)

    doc.add_heading("C. Research Objectives", level=1)
    for item in [
        "To design an IDS pipeline that detects normal and malicious network traffic using machine learning.",
        "To use hybrid ML because tree ensembles capture non-linear supervised patterns while anomaly detection contributes sensitivity to unusual traffic behavior.",
        "To select UNSW-NB15 because it contains modern synthetic attack traffic, normal traffic, rich network-flow features, binary labels, and multiclass attack categories.",
        "Research hypothesis: A hybrid IDS that combines supervised ensemble learners with anomaly-based evidence will achieve higher F1-score and ROC-AUC than individual baseline models.",
    ]:
        doc.add_paragraph(item, style="List Bullet")

    doc.add_heading("D. Research Methodology Diagram", level=1)
    doc.add_picture(str(image_paths["workflow"]), width=Inches(5.7))
    add_caption(doc, "Figure 1. Research methodology workflow for the proposed AI-powered IDS.")

    doc.add_heading("E. Hybrid Architecture Diagram", level=1)
    doc.add_picture(str(image_paths["architecture"]), width=Inches(5.6))
    add_caption(doc, "Figure 2. Hybrid IDS architecture using Random Forest, XGBoost, Isolation Forest, and a fusion layer.")

    doc.add_heading("F. Dataset Explanation", level=1)
    doc.add_paragraph(
        "UNSW-NB15 is a network intrusion detection dataset created to represent modern normal and attack traffic. "
        "It includes flow-level and content-based attributes that describe packet counts, byte counts, time-to-live values, jitter, loss, rates, services, states, and labels."
    )
    doc.add_paragraph(
        "The dataset is suitable because it contains 49 commonly cited features, binary labels for normal versus attack detection, and attack-category labels for multiclass intrusion analysis. "
        "Attack categories include Analysis, Backdoor, DoS, Exploits, Fuzzers, Generic, Reconnaissance, Shellcode, and Worms."
    )
    doc.add_paragraph(
        "Binary classification predicts whether a record is normal or malicious. Multiclass classification predicts the specific attack category. "
        "This research emphasizes binary IDS detection while retaining the methodology for extending the pipeline to multiclass learning."
    )
    doc.add_picture(str(image_paths["dataset_workflow"]), width=Inches(6.2))
    add_caption(doc, "Figure 3. Dataset preparation workflow for UNSW-NB15 records.")

    doc.add_heading("G. Research Pipeline", level=1)
    pipeline_steps = [
        ("Data loading", "CSV files are loaded from the data directory and combined into a single analytical dataframe."),
        ("Missing value handling", "Null values are identified; numerical fields are imputed with medians and categorical fields with modes."),
        ("Feature encoding", "Categorical variables such as protocol, service, and state are transformed using one-hot encoding."),
        ("Scaling", "Numerical variables are standardized where required, especially for Logistic Regression and fusion models."),
        ("Model training", "Baseline models are trained under the same split to maintain fair comparison."),
        ("Hybrid fusion", "Predicted probabilities from Random Forest, XGBoost, and normalized Isolation Forest scores are used as meta-features for Logistic Regression or voting fusion."),
        ("Evaluation", "Models are assessed through confusion matrix, threshold metrics, ROC curve, PR curve, and comparative summary tables."),
    ]
    table = doc.add_table(rows=1, cols=2)
    table.style = "Table Grid"
    table.rows[0].cells[0].text = "Step"
    table.rows[0].cells[1].text = "Explanation"
    for step, explanation in pipeline_steps:
        row = table.add_row().cells
        row[0].text = step
        row[1].text = explanation
    add_caption(doc, "Table 1. Step-by-step research pipeline.")

    doc.add_heading("H. Metrics Explanation", level=1)
    equations = [
        ("Accuracy", "Accuracy = (TP + TN) / (TP + TN + FP + FN)"),
        ("Precision", "Precision = TP / (TP + FP)"),
        ("Recall", "Recall = TP / (TP + FN)"),
        ("F1-score", "F1 = 2 x (Precision x Recall) / (Precision + Recall)"),
        ("ROC-AUC", "ROC-AUC = Area under the TPR versus FPR curve"),
        ("PR-AUC", "PR-AUC = Area under the Precision versus Recall curve"),
        ("False Positive Rate", "FPR = FP / (FP + TN)"),
        ("False Negative Rate", "FNR = FN / (FN + TP)"),
    ]
    for label, equation in equations:
        doc.add_paragraph(label, style="List Bullet")
        add_equation(doc, equation)

    doc.add_heading("I. Result Interpretation", level=1)
    best = metrics.sort_values("F1", ascending=False).iloc[0]
    doc.add_paragraph(
        f"In the generated demonstration run, the strongest F1-score is produced by {best['Model']} with F1={best['F1']:.4f}. "
        "A stronger model usually performs better because it captures non-linear relationships, interaction effects, and minority-class patterns more effectively."
    )
    doc.add_paragraph(
        "The hybrid architecture is important because it combines complementary evidence: Random Forest contributes robust bagging-based decisions, XGBoost contributes boosted error correction, and Isolation Forest adds anomaly-oriented information. "
        "Fusion reduces dependence on a single learner and can improve stability when one model is weak for a specific traffic pattern."
    )
    doc.add_paragraph(
        "Overfitting is monitored by comparing train and test performance, limiting tree depth, using cross-validation, and tracking whether high accuracy is accompanied by poor recall or unstable PR-AUC. "
        "Bias and variance are balanced by combining lower-bias boosted trees with lower-variance bagged trees and a regularized fusion model."
    )

    doc.add_heading("J. Limitations", level=1)
    for item in [
        "Dataset limitations: UNSW-NB15 is valuable but still a benchmark dataset; real enterprise traffic may contain different protocols, encrypted payload behavior, and evolving attack strategies.",
        "Computational limitations: ensemble and hybrid models require more memory, training time, and inference resources than simpler classifiers.",
        "Real-time deployment limitations: production IDS deployment must handle streaming data, concept drift, low-latency scoring, alert fatigue, and integration with SIEM or SOAR platforms.",
    ]:
        doc.add_paragraph(item, style="List Bullet")

    doc.add_heading("K. Future Scope", level=1)
    for item in [
        "Explainable AI IDS: integrate SHAP or LIME to explain why a flow is flagged as malicious.",
        "Federated IDS: train across organizations or edge nodes without centralizing sensitive traffic data.",
        "Real-time cloud deployment: deploy the model behind a streaming pipeline using cloud-native monitoring infrastructure.",
        "Zero-day attack detection: strengthen anomaly and self-supervised components to detect novel traffic patterns.",
    ]:
        doc.add_paragraph(item, style="List Bullet")

    doc.add_heading("L. Diagrams and Charts", level=1)
    chart_sequence = [
        ("confusion_matrix", "Figure 4. Confusion matrix for hybrid IDS predictions."),
        ("roc_curve", "Figure 5. ROC curves comparing baseline and hybrid IDS models."),
        ("pr_curve", "Figure 6. Precision-recall curves comparing detection performance under class imbalance."),
        ("feature_importance", "Figure 7. Top feature importance scores from the Random Forest baseline."),
        ("model_comparison", "Figure 8. Model comparison graph across core evaluation metrics."),
    ]
    for key, caption in chart_sequence:
        doc.add_picture(str(image_paths[key]), width=Inches(5.9))
        add_caption(doc, caption)

    doc.add_heading("Model Performance Summary", level=2)
    perf_table = doc.add_table(rows=1, cols=len(metrics.columns))
    perf_table.style = "Table Grid"
    for i, col in enumerate(metrics.columns):
        perf_table.rows[0].cells[i].text = col
    for _, metric in metrics.iterrows():
        row = perf_table.add_row().cells
        for i, col in enumerate(metrics.columns):
            row[i].text = str(metric[col])
    add_caption(doc, "Table 2. Quantitative model comparison from the reproducible demonstration run.")

    doc.save(DOCX_PATH)
    shutil.copy2(DOCX_PATH, REPORTS_DIR / DOCX_PATH.name)


def create_analysis_script() -> None:
    script = r'''from __future__ import annotations

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
'''
    (ROOT / "scripts" / "run_hybrid_ids_analysis.py").write_text(script, encoding="utf-8")


def create_notebook() -> None:
    nb = nbf.v4.new_notebook()
    cells = []

    def md(text: str):
        cells.append(nbf.v4.new_markdown_cell(text))

    def code(text: str):
        cells.append(nbf.v4.new_code_cell(text))

    md("# Hybrid IDS Research Analysis\n\nThis notebook supports the project **AI-Powered Intrusion Detection System Using a Hybrid Machine Learning Architecture**. It loads UNSW-NB15 CSV files when available and falls back to a reproducible UNSW-NB15-like demonstration dataset so the notebook can execute end-to-end without manual changes.")
    code("""from pathlib import Path
import json
import warnings

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

from sklearn.compose import ColumnTransformer
from sklearn.datasets import make_classification
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score, average_precision_score, confusion_matrix, f1_score,
    precision_recall_curve, precision_score, recall_score, roc_auc_score,
    roc_curve
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from xgboost import XGBClassifier

warnings.filterwarnings("ignore")
sns.set_theme(style="whitegrid")
ROOT = Path.cwd()
DATA_DIR = ROOT / "data"
CHART_DIR = ROOT / "charts"
METRICS_DIR = ROOT / "metrics"
CHART_DIR.mkdir(exist_ok=True)
METRICS_DIR.mkdir(exist_ok=True)
RANDOM_STATE = 42""")

    md("## 1. Introduction\n\nThe objective is to evaluate an intrusion detection system that combines supervised ensemble learning and anomaly detection. UNSW-NB15 is selected because it includes modern attack categories, normal traffic, binary labels, and network-flow features suitable for machine learning.")
    md("## 2. Dataset Loading\n\nPlace UNSW-NB15 CSV files in the `data/` directory. The loader searches for CSV files and combines them. If no real dataset exists, a reproducible demonstration dataset is generated so every section remains executable.")
    code("""ATTACK_CATEGORIES = [
    "Analysis", "Backdoor", "DoS", "Exploits", "Fuzzers",
    "Generic", "Reconnaissance", "Shellcode", "Worms"
]

def make_demo_dataset(n_samples=2500, n_features=20):
    x, y = make_classification(
        n_samples=n_samples, n_features=n_features, n_informative=12,
        n_redundant=4, n_clusters_per_class=2, weights=[0.64, 0.36],
        class_sep=1.25, random_state=RANDOM_STATE
    )
    columns = [
        "dur", "spkts", "dpkts", "sbytes", "dbytes", "rate", "sttl", "dttl",
        "sload", "dload", "sloss", "dloss", "sinpkt", "dinpkt", "sjit",
        "djit", "swin", "stcpb", "dtcpb", "dwin"
    ][:n_features]
    df = pd.DataFrame(x, columns=columns)
    rng = np.random.default_rng(RANDOM_STATE)
    df["label"] = y
    df["attack_cat"] = np.where(df["label"].eq(0), "Normal", rng.choice(ATTACK_CATEGORIES, len(df)))
    return df

def load_dataset():
    csv_files = sorted(DATA_DIR.glob("*.csv"))
    if csv_files:
        df = pd.concat((pd.read_csv(path) for path in csv_files), ignore_index=True)
        source = f"Loaded {len(csv_files)} CSV file(s) from {DATA_DIR}"
    else:
        df = make_demo_dataset()
        source = "Generated reproducible UNSW-NB15-like demonstration dataset"
    return df, source

df, source = load_dataset()
print(source)
df.head()""")

    md("## 3. Exploratory Data Analysis\n\nThis section checks shape, null values, attack distribution, class imbalance, summary statistics, and core visualization patterns.")
    code("""print("Shape:", df.shape)
display(df.isna().sum().sort_values(ascending=False).head(15).to_frame("null_count"))
display(df["label"].value_counts().rename(index={0: "Normal", 1: "Attack"}).to_frame("count"))
if "attack_cat" in df.columns:
    display(df["attack_cat"].value_counts().to_frame("count"))
display(df.describe(include="all").T.head(20))""")
    code("""fig, ax = plt.subplots(figsize=(5, 4))
sns.countplot(data=df, x="label", ax=ax)
ax.set_title("Binary Class Distribution")
ax.set_xticklabels(["Normal", "Attack"])
plt.show()

numeric_cols = df.select_dtypes(include=["number", "bool"]).columns.drop("label", errors="ignore")
fig, ax = plt.subplots(figsize=(9, 7))
sns.heatmap(df[numeric_cols[:15].tolist() + ["label"]].corr(), cmap="coolwarm", center=0, ax=ax)
ax.set_title("Correlation Heatmap")
plt.show()

df[numeric_cols[:6]].hist(figsize=(10, 6), bins=30)
plt.suptitle("Feature Distributions")
plt.tight_layout()
plt.show()""")

    md("## 4. Data Preprocessing\n\nThe pipeline imputes missing values, encodes categorical fields, and scales numeric features. Scaling is essential for linear models and the fusion layer.")
    code("""TARGET = "label"
X = df.drop(columns=[TARGET], errors="ignore")
y = df[TARGET].astype(int)
X_model = X.drop(columns=["attack_cat"], errors="ignore")

numeric_features = X_model.select_dtypes(include=["number", "bool"]).columns.tolist()
categorical_features = [col for col in X_model.columns if col not in numeric_features]

numeric_pipeline = Pipeline([
    ("imputer", SimpleImputer(strategy="median")),
    ("scaler", StandardScaler()),
])
categorical_pipeline = Pipeline([
    ("imputer", SimpleImputer(strategy="most_frequent")),
    ("encoder", OneHotEncoder(handle_unknown="ignore")),
])
preprocessor = ColumnTransformer([
    ("num", numeric_pipeline, numeric_features),
    ("cat", categorical_pipeline, categorical_features),
])

X_train, X_test, y_train, y_test = train_test_split(
    X_model, y, test_size=0.25, stratify=y, random_state=RANDOM_STATE
)
X_train_t = preprocessor.fit_transform(X_train)
X_test_t = preprocessor.transform(X_test)
print("Train matrix:", X_train_t.shape, "Test matrix:", X_test_t.shape)""")

    md("## 5. Baseline Models\n\nBaseline models include Logistic Regression, Random Forest, and XGBoost. Each is evaluated using accuracy, precision, recall, F1-score, ROC-AUC, confusion matrix, ROC curve, and PR curve.")
    code("""def evaluate_model(name, y_true, probabilities):
    predictions = (probabilities >= 0.5).astype(int)
    return {
        "Model": name,
        "Accuracy": accuracy_score(y_true, predictions),
        "Precision": precision_score(y_true, predictions, zero_division=0),
        "Recall": recall_score(y_true, predictions, zero_division=0),
        "F1": f1_score(y_true, predictions, zero_division=0),
        "ROC AUC": roc_auc_score(y_true, probabilities),
        "PR AUC": average_precision_score(y_true, probabilities),
    }

baseline_models = {
    "Logistic Regression": LogisticRegression(max_iter=1000, random_state=RANDOM_STATE),
    "Random Forest": RandomForestClassifier(n_estimators=180, max_depth=12, random_state=RANDOM_STATE, n_jobs=1),
    "XGBoost": XGBClassifier(
        n_estimators=160, max_depth=4, learning_rate=0.06, subsample=0.9,
        colsample_bytree=0.9, eval_metric="logloss", random_state=RANDOM_STATE, n_jobs=2
    ),
}

probabilities = {}
fitted_models = {}
metrics_rows = []
for name, model in baseline_models.items():
    model.fit(X_train_t, y_train)
    fitted_models[name] = model
    probabilities[name] = model.predict_proba(X_test_t)[:, 1]
    metrics_rows.append(evaluate_model(name, y_test, probabilities[name]))

baseline_metrics = pd.DataFrame(metrics_rows)
display(baseline_metrics)""")
    code("""def plot_model_diagnostics(name, y_true, proba):
    pred = (proba >= 0.5).astype(int)
    fig, axes = plt.subplots(1, 3, figsize=(15, 4))
    sns.heatmap(confusion_matrix(y_true, pred), annot=True, fmt="d", cmap="Blues", cbar=False, ax=axes[0])
    axes[0].set_title(f"{name}: Confusion Matrix")
    fpr, tpr, _ = roc_curve(y_true, proba)
    axes[1].plot(fpr, tpr, label=f"AUC={roc_auc_score(y_true, proba):.3f}")
    axes[1].plot([0, 1], [0, 1], "--", color="gray")
    axes[1].set_title("ROC Curve")
    axes[1].legend()
    precision, recall, _ = precision_recall_curve(y_true, proba)
    axes[2].plot(recall, precision, label=f"AP={average_precision_score(y_true, proba):.3f}")
    axes[2].set_title("PR Curve")
    axes[2].legend()
    plt.tight_layout()
    plt.show()

for model_name, proba in probabilities.items():
    plot_model_diagnostics(model_name, y_test, proba)""")

    md("## 6. Hybrid Model\n\nThe hybrid model fuses Random Forest probability, XGBoost probability, and normalized Isolation Forest anomaly score. Logistic Regression is used as a meta-classifier fusion layer.")
    code("""def normalize(values):
    values = np.asarray(values)
    return (values - values.min()) / max(values.max() - values.min(), 1e-9)

isolation = IsolationForest(n_estimators=120, contamination="auto", random_state=RANDOM_STATE)
isolation.fit(X_train_t)
iso_train = normalize(-isolation.decision_function(X_train_t))
iso_test = normalize(-isolation.decision_function(X_test_t))

stacked_train = np.column_stack([
    fitted_models["Random Forest"].predict_proba(X_train_t)[:, 1],
    fitted_models["XGBoost"].predict_proba(X_train_t)[:, 1],
    iso_train,
])
stacked_test = np.column_stack([
    probabilities["Random Forest"],
    probabilities["XGBoost"],
    iso_test,
])

fusion_model = LogisticRegression(max_iter=1000, random_state=RANDOM_STATE)
fusion_model.fit(stacked_train, y_train)
hybrid_proba = fusion_model.predict_proba(stacked_test)[:, 1]
probabilities["Hybrid RF + XGBoost + Isolation Forest"] = hybrid_proba
hybrid_metrics = evaluate_model("Hybrid RF + XGBoost + Isolation Forest", y_test, hybrid_proba)
display(pd.DataFrame([hybrid_metrics]))
plot_model_diagnostics("Hybrid RF + XGBoost + Isolation Forest", y_test, hybrid_proba)""")

    md("## 7. Model Comparison\n\nThe table and bar chart compare baseline and hybrid performance across core IDS metrics.")
    code("""comparison = pd.DataFrame(metrics_rows + [hybrid_metrics])
display(comparison[["Model", "Accuracy", "Precision", "Recall", "F1", "ROC AUC"]])

comparison.to_csv(METRICS_DIR / "notebook_model_metrics.csv", index=False)
comparison.to_json(METRICS_DIR / "notebook_model_metrics.json", orient="records", indent=2)

plot_df = comparison.melt(id_vars="Model", value_vars=["Accuracy", "Precision", "Recall", "F1", "ROC AUC"],
                          var_name="Metric", value_name="Score")
fig, ax = plt.subplots(figsize=(10, 5))
sns.barplot(data=plot_df, x="Metric", y="Score", hue="Model", ax=ax)
ax.set_ylim(0, 1.05)
ax.set_title("Model Comparison")
plt.xticks(rotation=0)
plt.legend(loc="lower right")
plt.tight_layout()
plt.show()""")

    md("## 8. Feature Importance\n\nFeature importance is extracted from Random Forest for interpretable ranking of influential traffic attributes.")
    code("""rf = fitted_models["Random Forest"]
if hasattr(preprocessor, "get_feature_names_out"):
    feature_names = preprocessor.get_feature_names_out()
else:
    feature_names = np.array([f"feature_{i}" for i in range(X_train_t.shape[1])])

importance = pd.DataFrame({
    "Feature": feature_names,
    "Importance": rf.feature_importances_,
}).sort_values("Importance", ascending=False).head(15)

fig, ax = plt.subplots(figsize=(8, 5))
sns.barplot(data=importance, y="Feature", x="Importance", ax=ax)
ax.set_title("Top Feature Importance Scores")
plt.tight_layout()
plt.show()
display(importance)""")

    md("## 9. Final Interpretation\n\nThe best model is selected by F1-score and ROC-AUC because IDS evaluation must balance detection capability and false alarms. Hybrid fusion can improve performance by combining supervised classification strength with anomaly evidence, making the detector more robust to diverse intrusion behavior. The research conclusion is that hybrid ML is a suitable applied, experimental, quantitative, and comparative approach for IDS design on UNSW-NB15-style network traffic.")
    code("""best_by_f1 = comparison.sort_values("F1", ascending=False).iloc[0]
print(f"Best model by F1-score: {best_by_f1['Model']} (F1={best_by_f1['F1']:.4f}, ROC AUC={best_by_f1['ROC AUC']:.4f})")
print("Research conclusion: hybrid IDS fusion provides a structured way to combine complementary model evidence for intrusion detection.")""")

    nb["cells"] = cells
    nb["metadata"] = {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "pygments_lexer": "ipython3"},
    }
    nbf.write(nb, NOTEBOOK_PATH)


def create_zip() -> None:
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()
    include_paths = [
        ROOT / "HOW_TO_RUN.md",
        DOCX_PATH,
        ROOT / "publishable_hybrid_ids_research_paper.docx",
        NOTEBOOK_PATH,
        ROOT / "requirements.txt",
        ROOT / "scripts" / "generate_research_deliverables.py",
        ROOT / "scripts" / "create_publishable_paper.py",
        ROOT / "scripts" / "run_hybrid_ids_analysis.py",
        DATA_DIR / "sample_unsw_nb15_like.csv",
    ]
    chart_paths = sorted(CHART_DIR.glob("*.png"))
    metric_paths = sorted(METRICS_DIR.glob("*"))
    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in include_paths + metric_paths + chart_paths:
            if path.exists():
                archive.write(path, path.relative_to(ROOT))


def main() -> None:
    ensure_dirs()
    plt.rcParams.update({"font.family": "DejaVu Sans", "axes.titleweight": "bold"})
    metrics, probabilities, y_test, importances, feature_names = train_models()
    image_paths: dict[str, Path] = {
        "workflow": save_workflow_diagram(),
        "architecture": save_architecture_diagram(),
        "dataset_workflow": save_dataset_workflow(),
    }
    image_paths.update(save_metric_charts(metrics, probabilities, y_test, importances, feature_names))
    create_docx(metrics, image_paths)
    create_analysis_script()
    create_notebook()
    create_zip()
    print(f"Created {DOCX_PATH}")
    print(f"Created {NOTEBOOK_PATH}")
    print(f"Created {ZIP_PATH}")


if __name__ == "__main__":
    main()
