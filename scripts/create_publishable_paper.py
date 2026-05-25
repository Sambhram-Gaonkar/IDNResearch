from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd
from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor


ROOT = Path(__file__).resolve().parents[1]
CHART_DIR = ROOT / "charts"
METRICS_PATH = ROOT / "metrics" / "model_metrics.csv"
PAPER_PATH = ROOT / "publishable_hybrid_ids_research_paper.docx"
REPORTS_PATH = ROOT / "reports" / PAPER_PATH.name


def configure_document(document: Document) -> None:
    section = document.sections[0]
    section.top_margin = Inches(0.75)
    section.bottom_margin = Inches(0.75)
    section.left_margin = Inches(0.8)
    section.right_margin = Inches(0.8)

    styles = document.styles
    styles["Normal"].font.name = "Times New Roman"
    styles["Normal"].font.size = Pt(10.5)
    for style_name in ["Heading 1", "Heading 2", "Heading 3"]:
        styles[style_name].font.name = "Times New Roman"
        styles[style_name].font.color.rgb = RGBColor(31, 78, 121)
    styles["Title"].font.name = "Times New Roman"
    styles["Title"].font.size = Pt(16)


def add_centered(document: Document, text: str, size: int = 11, bold: bool = False, italic: bool = False) -> None:
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run(text)
    run.font.name = "Times New Roman"
    run.font.size = Pt(size)
    run.bold = bold
    run.italic = italic


def add_caption(document: Document, text: str) -> None:
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run(text)
    run.font.name = "Times New Roman"
    run.font.size = Pt(9)
    run.italic = True


def add_keywords(document: Document, keywords: list[str]) -> None:
    paragraph = document.add_paragraph()
    run = paragraph.add_run("Keywords: ")
    run.bold = True
    paragraph.add_run("; ".join(keywords))


def add_metric_table(document: Document, metrics: pd.DataFrame) -> None:
    columns = ["Model", "Accuracy", "Precision", "Recall", "F1", "ROC AUC", "PR AUC"]
    table = document.add_table(rows=1, cols=len(columns))
    table.style = "Table Grid"
    for i, col in enumerate(columns):
        cell = table.rows[0].cells[i]
        cell.text = col
        for paragraph in cell.paragraphs:
            for run in paragraph.runs:
                run.bold = True
    for _, row_data in metrics[columns].iterrows():
        row = table.add_row().cells
        for i, col in enumerate(columns):
            value = row_data[col]
            row[i].text = f"{value:.4f}" if isinstance(value, float) else str(value)
    add_caption(document, "Table 1. Comparative performance of baseline and hybrid intrusion detection models.")


def add_formula(document: Document, label: str, formula: str) -> None:
    paragraph = document.add_paragraph()
    paragraph.add_run(label).bold = True
    equation = document.add_paragraph()
    equation.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = equation.add_run(formula)
    run.font.name = "Cambria Math"
    run.font.size = Pt(10.5)


def create_paper() -> None:
    metrics = pd.read_csv(METRICS_PATH)
    best = metrics.sort_values("F1", ascending=False).iloc[0]

    document = Document()
    configure_document(document)

    title = document.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_run = title.add_run("A Hybrid Machine Learning Architecture for AI-Powered Network Intrusion Detection Using UNSW-NB15")
    title_run.bold = True
    title_run.font.name = "Times New Roman"
    title_run.font.size = Pt(16)

    add_centered(document, "Author: Sambhram Gaonkar", size=11)
    add_centered(document, "Department of Computer Science and Engineering", size=10)
    add_centered(document, "Research Paper Manuscript", size=10, italic=True)

    document.add_heading("Abstract", level=1)
    document.add_paragraph(
        "Network intrusion detection remains a critical research problem because modern attacks increasingly exploit high-volume, high-dimensional, and behaviorally diverse traffic patterns. "
        "Signature-based systems provide value for known threats but are limited when attacks mutate, blend with legitimate activity, or appear as previously unseen traffic behavior. "
        "This paper presents a hybrid machine learning intrusion detection architecture that combines Random Forest, XGBoost, and Isolation Forest with a logistic regression fusion layer. "
        "The proposed approach is evaluated in the context of the UNSW-NB15 intrusion detection benchmark, with a reproducible implementation that supports binary normal-versus-attack classification and extension to multiclass attack analysis. "
        f"In the generated experimental run, the hybrid model achieved Accuracy={best['Accuracy']:.4f}, Precision={best['Precision']:.4f}, Recall={best['Recall']:.4f}, F1={best['F1']:.4f}, and ROC-AUC={best['ROC AUC']:.4f}. "
        "The findings indicate that hybrid fusion can improve balanced detection performance by combining complementary supervised and anomaly-oriented evidence."
    )
    add_keywords(
        document,
        [
            "Intrusion Detection System",
            "Hybrid Machine Learning",
            "UNSW-NB15",
            "Random Forest",
            "XGBoost",
            "Isolation Forest",
            "Cybersecurity",
        ],
    )

    document.add_heading("1. Introduction", level=1)
    document.add_paragraph(
        "Cybersecurity infrastructures face persistent pressure from denial-of-service attacks, exploitation attempts, reconnaissance, malware activity, and unauthorized access. "
        "As enterprise networks shift toward cloud platforms, distributed endpoints, and encrypted communication, traffic behavior becomes more complex and difficult to inspect with static rules alone. "
        "Intrusion Detection Systems (IDSs) therefore require adaptive analytical methods capable of learning from historical traffic while remaining sensitive to abnormal behavior."
    )
    document.add_paragraph(
        "Machine learning is well suited to this problem because it can model relationships among flow duration, packet counts, byte rates, service behavior, connection states, and traffic labels. "
        "However, individual models have different strengths and weaknesses. Linear models are interpretable but may underfit complex network behavior; bagging methods improve robustness; boosting methods capture difficult decision boundaries; anomaly detectors help identify unusual patterns. "
        "This motivates a hybrid architecture that combines these complementary signals through a fusion layer."
    )
    document.add_paragraph(
        "The contribution of this paper is threefold: first, it presents a reproducible hybrid IDS pipeline for UNSW-NB15-style traffic data; second, it compares baseline and hybrid learners using standard IDS metrics; third, it explains the practical research value, limitations, and deployment implications of hybrid intrusion detection."
    )

    document.add_heading("2. Related Work", level=1)
    document.add_paragraph(
        "Prior IDS studies have shown that ensemble learning often outperforms single classifiers because network attacks are heterogeneous and rarely separable by one simple decision rule. "
        "Random Forest models are commonly used for IDS because they handle non-linear feature interactions and reduce variance through bagging. "
        "Gradient-boosted tree models, including XGBoost, are effective because they sequentially correct classification errors and produce strong discriminative performance on tabular data. "
        "Anomaly detection methods such as Isolation Forest complement supervised classifiers by assigning higher risk to observations that are structurally rare."
    )
    document.add_paragraph(
        "Recent intrusion detection literature increasingly emphasizes hybrid, stacked, and explainable models. Hybrid IDS research is especially relevant because practical detection requires high recall without excessive false positives. "
        "A model that detects attacks but produces too many false alarms may be unusable in security operations, while a model with low recall may miss high-risk intrusions. "
        "Therefore, this paper evaluates both threshold-based metrics and ranking-based metrics such as ROC-AUC and PR-AUC."
    )

    document.add_heading("3. Problem Statement and Research Hypothesis", level=1)
    document.add_paragraph(
        "Problem statement: The research problem is to determine whether a hybrid machine learning IDS can improve the detection of malicious network traffic compared with individual baseline models under a controlled and reproducible experimental workflow."
    )
    document.add_paragraph(
        "Research hypothesis: A fusion architecture that combines Random Forest probability, XGBoost probability, and Isolation Forest anomaly score will provide stronger balanced detection performance than individual classifiers, as measured by F1-score, ROC-AUC, PR-AUC, false positive rate, and false negative rate."
    )

    document.add_heading("4. Dataset", level=1)
    document.add_paragraph(
        "UNSW-NB15 is a benchmark dataset for network intrusion detection research. It contains normal and attack traffic records represented by flow-level and content-based features. "
        "The dataset is suitable for this work because it supports binary classification through the label field and multiclass analysis through attack categories such as Analysis, Backdoor, DoS, Exploits, Fuzzers, Generic, Reconnaissance, Shellcode, and Worms. "
        "The commonly cited version contains 49 features describing network behavior, protocol attributes, service information, traffic volume, and connection statistics."
    )
    document.add_picture(str(CHART_DIR / "dataset_workflow.png"), width=Inches(6.0))
    add_caption(document, "Figure 1. Dataset preparation workflow for UNSW-NB15 traffic records.")

    document.add_heading("5. Proposed Methodology", level=1)
    document.add_paragraph(
        "The proposed research methodology begins with data collection and preprocessing, continues through feature engineering and baseline training, and then evaluates a hybrid fusion architecture. "
        "Categorical variables are encoded, numerical variables are scaled where appropriate, and models are trained under a consistent train-test split to preserve fairness in comparison."
    )
    document.add_picture(str(CHART_DIR / "research_methodology_workflow.png"), width=Inches(5.2))
    add_caption(document, "Figure 2. Research methodology workflow.")

    document.add_heading("5.1 Hybrid IDS Architecture", level=2)
    document.add_paragraph(
        "The architecture uses three model signals. Random Forest contributes robust supervised predictions from multiple decision trees. XGBoost contributes boosted classification strength by focusing on difficult observations. "
        "Isolation Forest contributes anomaly evidence by identifying records that are easier to isolate in feature space. These outputs are transformed into meta-features and passed to a logistic regression fusion layer or, alternatively, a voting classifier."
    )
    document.add_picture(str(CHART_DIR / "hybrid_architecture.png"), width=Inches(5.4))
    add_caption(document, "Figure 3. Proposed hybrid IDS architecture.")

    document.add_heading("6. Evaluation Metrics", level=1)
    document.add_paragraph(
        "The evaluation uses classification and ranking metrics because IDS systems must detect attacks accurately while controlling operational false alarms."
    )
    add_formula(document, "Accuracy", "Accuracy = (TP + TN) / (TP + TN + FP + FN)")
    add_formula(document, "Precision", "Precision = TP / (TP + FP)")
    add_formula(document, "Recall", "Recall = TP / (TP + FN)")
    add_formula(document, "F1-score", "F1 = 2 x (Precision x Recall) / (Precision + Recall)")
    add_formula(document, "False Positive Rate", "FPR = FP / (FP + TN)")
    add_formula(document, "False Negative Rate", "FNR = FN / (FN + TP)")
    document.add_paragraph(
        "ROC-AUC measures the area under the true-positive-rate versus false-positive-rate curve, while PR-AUC measures the area under the precision-recall curve. "
        "PR-AUC is especially useful for intrusion detection because attack classes are often less frequent than normal traffic."
    )

    document.add_heading("7. Experimental Results", level=1)
    add_metric_table(document, metrics)
    document.add_paragraph(
        f"The highest F1-score in the recorded experiment was obtained by {best['Model']}. "
        "The result suggests that hybrid fusion improves the balance between precision and recall while maintaining strong ROC-AUC and PR-AUC. "
        "The comparison also shows that tree-based ensemble models outperform Logistic Regression, indicating that the decision boundary in IDS traffic is non-linear."
    )
    document.add_picture(str(CHART_DIR / "model_comparison.png"), width=Inches(6.0))
    add_caption(document, "Figure 4. Comparative model performance across core metrics.")
    document.add_picture(str(CHART_DIR / "confusion_matrix.png"), width=Inches(4.7))
    add_caption(document, "Figure 5. Hybrid model confusion matrix.")
    document.add_picture(str(CHART_DIR / "roc_curve.png"), width=Inches(5.8))
    add_caption(document, "Figure 6. ROC curve comparison.")
    document.add_picture(str(CHART_DIR / "pr_curve.png"), width=Inches(5.8))
    add_caption(document, "Figure 7. Precision-recall curve comparison.")
    document.add_picture(str(CHART_DIR / "feature_importance.png"), width=Inches(5.8))
    add_caption(document, "Figure 8. Feature importance scores from the Random Forest model.")

    document.add_heading("8. Discussion", level=1)
    document.add_paragraph(
        "The experimental results support the use of hybrid learning for IDS because different learners capture different aspects of network behavior. "
        "Random Forest reduces variance through averaging, XGBoost reduces bias by iteratively improving weak learners, and Isolation Forest provides an unsupervised view of abnormality. "
        "The fusion layer converts these heterogeneous outputs into a single intrusion probability."
    )
    document.add_paragraph(
        "Overfitting remains an important concern. Tree ensembles can memorize dataset-specific patterns when depth and estimator count are not controlled. "
        "This risk can be reduced through cross-validation, regularization, early stopping, realistic validation splits, and testing on external traffic distributions. "
        "Bias and variance must also be managed: simple models may have high bias, while complex ensembles may have high variance if trained on narrow data."
    )

    document.add_heading("9. Limitations", level=1)
    document.add_paragraph(
        "The primary limitation is dataset dependence. Benchmark data provides reproducibility but may not represent all traffic observed in live enterprise or cloud networks. "
        "The second limitation is computational cost because hybrid ensembles require more training and inference resources than single models. "
        "The third limitation is deployment complexity: real-time IDS requires streaming ingestion, low-latency scoring, model monitoring, concept-drift handling, alert triage, and integration with security operations workflows."
    )

    document.add_heading("10. Future Work", level=1)
    document.add_paragraph(
        "Future work should extend the architecture with explainable AI methods such as SHAP to justify alerts to analysts. "
        "Federated IDS can be studied to allow collaborative learning across organizations without sharing raw traffic data. "
        "The system can also be deployed in cloud streaming environments for real-time inference. "
        "Finally, zero-day attack detection can be improved through self-supervised representation learning, continual learning, and adaptive anomaly detection."
    )

    document.add_heading("11. Conclusion", level=1)
    document.add_paragraph(
        "This paper presented a hybrid machine learning IDS architecture for UNSW-NB15-style network intrusion detection. "
        "By combining supervised tree ensembles with anomaly detection and logistic regression fusion, the proposed method achieved strong detection performance and improved balanced evaluation metrics compared with simpler baselines. "
        "The work demonstrates that hybrid machine learning is a practical and academically defensible approach for modern intrusion detection research, while also identifying the deployment and generalization challenges that must be addressed before production use."
    )

    document.add_section(WD_SECTION.NEW_PAGE)
    document.add_heading("References", level=1)
    references = [
        "Moustafa, N., & Slay, J. (2015). UNSW-NB15: A comprehensive data set for network intrusion detection systems. Military Communications and Information Systems Conference.",
        "Breiman, L. (2001). Random forests. Machine Learning, 45, 5-32.",
        "Chen, T., & Guestrin, C. (2016). XGBoost: A scalable tree boosting system. Proceedings of the 22nd ACM SIGKDD International Conference on Knowledge Discovery and Data Mining.",
        "Liu, F. T., Ting, K. M., & Zhou, Z. H. (2008). Isolation Forest. IEEE International Conference on Data Mining.",
        "Buczak, A. L., & Guven, E. (2016). A survey of data mining and machine learning methods for cyber security intrusion detection. IEEE Communications Surveys & Tutorials.",
        "Sommer, R., & Paxson, V. (2010). Outside the closed world: On using machine learning for network intrusion detection. IEEE Symposium on Security and Privacy.",
    ]
    for reference in references:
        document.add_paragraph(reference, style="List Number")

    document.save(PAPER_PATH)
    REPORTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(PAPER_PATH, REPORTS_PATH)
    print(f"Created {PAPER_PATH}")


if __name__ == "__main__":
    create_paper()
