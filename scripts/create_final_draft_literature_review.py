from __future__ import annotations

from pathlib import Path
import re

import pandas as pd
from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

try:
    from generate_updated_real_unsw_paper import REFERENCES
except ModuleNotFoundError:
    from scripts.generate_updated_real_unsw_paper import REFERENCES


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "reports" / "FinalDraft.docx"
CHART_DIR = ROOT / "charts"
METRIC_DIR = ROOT / "metrics"
PAPER_DIR = ROOT / "references" / "papers"


CITATION_FILES = {
    1: "2026_liteshield_hybrid_feature_selection_ids.pdf",
    2: "2026_hossain_generalisation_intrusion_detection.pdf",
    3: "2026_alhusseini_ai_powered_hybrid_ids_cloud_security.pdf",
    4: "2026_hussein_repas_hybrid_intrusion_detection_autoencoder_ml.pdf",
    5: "2026_rigorous_comparative_supervised_ml_unsw_nb15.pdf",
    6: "2025_scientific_reports_network_based_intrusion_detection_deep_learning.pdf",
    7: "2025_botnet_detection_iot_stacked_ensemble_scientific_reports.pdf",
    8: "2025_negative_selection_anomaly_samples_nids_scientific_reports.pdf",
    9: "2025_xids_ensembleguard_explainable_ensemble_ids.pdf",
    10: "2025_stacked_machine_learning_unsw_nb15.pdf",
    11: "2025_intrusion_detection_ensemble_classification_feature_selection_scientific_reports.pdf",
    12: "2024_equilibrium_optimization_feature_selection_nids_scientific_reports.pdf",
    13: "2024_explainable_ai_comparative_intrusion_detection_models.pdf",
    14: "2022_zoghi_serpen_ensemble_classifier_unsw_nb15.pdf",
    15: "2022_igrf_rfe_hybrid_feature_selection_unsw_nb15.pdf",
    16: "2021_unsw_nb15_dataset_analysis_visualization.pdf",
}


def set_style(doc: Document) -> None:
    section = doc.sections[0]
    section.top_margin = Inches(0.75)
    section.bottom_margin = Inches(0.75)
    section.left_margin = Inches(0.85)
    section.right_margin = Inches(0.85)
    styles = doc.styles
    styles["Normal"].font.name = "Times New Roman"
    styles["Normal"].font.size = Pt(10.5)
    for name in ("Heading 1", "Heading 2", "Heading 3"):
        styles[name].font.name = "Times New Roman"
        styles[name].font.color.rgb = RGBColor(31, 78, 121)


def add_centered(doc: Document, text: str, size: int = 11, bold: bool = False, italic: bool = False) -> None:
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run(text)
    run.font.name = "Times New Roman"
    run.font.size = Pt(size)
    run.bold = bold
    run.italic = italic


def caption(doc: Document, text: str) -> None:
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run(text)
    run.italic = True
    run.font.size = Pt(9)


def bullet(doc: Document, text: str) -> None:
    doc.add_paragraph(text, style="List Bullet")


def numbered(doc: Document, text: str) -> None:
    doc.add_paragraph(text, style="List Number")


def add_hyperlink(paragraph, text: str, target: Path) -> None:
    relationship_id = paragraph.part.relate_to(
        str(target.resolve()),
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
        is_external=True,
    )
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), relationship_id)

    run = OxmlElement("w:r")
    properties = OxmlElement("w:rPr")
    color = OxmlElement("w:color")
    color.set(qn("w:val"), "0563C1")
    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    properties.append(color)
    properties.append(underline)
    run.append(properties)
    text_element = OxmlElement("w:t")
    text_element.text = text
    run.append(text_element)
    hyperlink.append(run)
    paragraph._p.append(hyperlink)


def cited_paragraph(doc: Document, text: str):
    paragraph = doc.add_paragraph()
    cursor = 0
    for match in re.finditer(r"\[(\d+)\]", text):
        if match.start() > cursor:
            paragraph.add_run(text[cursor : match.start()])
        citation_number = int(match.group(1))
        paper_file = CITATION_FILES.get(citation_number)
        if paper_file:
            add_hyperlink(paragraph, match.group(0), PAPER_DIR / paper_file)
        else:
            paragraph.add_run(match.group(0))
        cursor = match.end()
    if cursor < len(text):
        paragraph.add_run(text[cursor:])
    return paragraph


def add_table(doc: Document, df: pd.DataFrame, columns: list[str], title: str) -> None:
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
        ("2021 UNSW-NB15 visualization [16]", "UNSW-NB15", "Dataset analysis", "Showed the need for exploratory dataset understanding."),
        ("Zoghi & Serpen [14]", "UNSW-NB15", "Ensemble classifiers", "Linked classifier design to dataset characteristics."),
        ("Yin et al. [15]", "UNSW-NB15", "Hybrid feature selection", "Showed feature relevance affects IDS generalization."),
        ("Explainable AI study [13]", "UNSW-NB15", "XAI comparison", "Connected performance with interpretability."),
        ("xIDS-EnsembleGuard [9]", "Multiple IDS datasets", "Explainable ensemble", "Highlighted ensemble robustness and bias concerns."),
        ("LiteShield [1]", "UNSW-NB15", "Lightweight hybrid feature selection", "Emphasized deployability and constrained environments."),
        ("Hossain et al. [2]", "Multiple IDS datasets", "Generalization analysis", "Showed benchmark performance may not transfer."),
    ]
    table = doc.add_table(rows=1, cols=4)
    table.style = "Table Grid"
    for idx, header in enumerate(["Study", "Dataset", "Method", "Argument Relevance"]):
        table.rows[0].cells[idx].text = header
    for row in rows:
        cells = table.add_row().cells
        for idx, value in enumerate(row):
            cells[idx].text = value
    caption(doc, "Table 1. Literature positioning used to motivate the proposed hybrid IDS.")


def add_dataset_table(doc: Document) -> None:
    rows = [
        ("Training", "175,341", "56,000", "119,341", "10"),
        ("Testing", "82,332", "37,000", "45,332", "10"),
    ]
    table = doc.add_table(rows=1, cols=5)
    table.style = "Table Grid"
    for idx, header in enumerate(["Split", "Records", "Normal", "Attack", "Attack families"]):
        table.rows[0].cells[idx].text = header
    for row in rows:
        cells = table.add_row().cells
        for idx, value in enumerate(row):
            cells[idx].text = value
    caption(doc, "Table 2. Official UNSW-NB15 train/test split used in this study.")


def main() -> None:
    binary = pd.read_csv(METRIC_DIR / "journal_binary_metrics.csv")
    threshold = pd.read_csv(METRIC_DIR / "journal_threshold_metrics.csv")
    multiclass_summary = pd.read_csv(METRIC_DIR / "journal_multiclass_summary.csv")
    multiclass_detail = pd.read_csv(METRIC_DIR / "journal_multiclass_per_class.csv")
    best = binary.iloc[0]
    hybrid = binary[binary["Model"].eq("Fusion RF + XGBoost + IF")].iloc[0]
    xgb = binary[binary["Model"].eq("XGBoost")].iloc[0]

    doc = Document()
    set_style(doc)

    add_centered(doc, "Hybrid Supervised and Anomaly-Based Intrusion Detection on the UNSW-NB15 Dataset", size=16, bold=True)
    add_centered(doc, "Final Draft Research Paper", size=12, italic=True)

    doc.add_heading("Abstract", level=1)
    cited_paragraph(
        doc,
        f"Intrusion detection systems must identify malicious network behavior while controlling false alarms and missed attacks. Recent literature shows that tree-based supervised models, feature selection, explainable ensembles, and anomaly detection each improve parts of the problem, but their combined value requires careful empirical evaluation [1], [2], [4], [5], [9], [14], [16]. This paper studies a hybrid intrusion detection architecture on the official UNSW-NB15 train/test split using Random Forest, XGBoost, and Isolation Forest. Binary experiments compare Logistic Regression, Random Forest, XGBoost, Isolation Forest scoring, RF+XGBoost fusion, and RF+XGBoost+Isolation Forest fusion. Multiclass experiments evaluate attack-family detection using XGBoost. At the default threshold, {best['Model']} achieved the strongest binary F1-score of {best['F1']:.4f}; XGBoost achieved F1={xgb['F1']:.4f}, while the full hybrid achieved F1={hybrid['F1']:.4f}. The findings show that XGBoost remains the strongest default operating point, while the hybrid architecture provides a controlled framework for studying supervised confidence and anomaly-oriented evidence together."
    )
    paragraph = doc.add_paragraph()
    paragraph.add_run("Keywords: ").bold = True
    paragraph.add_run("Intrusion detection system, UNSW-NB15, Random Forest, XGBoost, Isolation Forest, hybrid machine learning, anomaly detection, cybersecurity")

    doc.add_heading("1. Introduction", level=1)
    doc.add_paragraph(
        "Modern networks support cloud services, IoT devices, remote users, and high-volume application traffic. This connectivity expands the attack surface and increases the need for automated intrusion detection. Signature-based intrusion detection remains useful for known attacks, but it is less effective against evolving traffic patterns and previously unseen behavior. Machine learning has therefore become a central direction in intrusion detection research because it can learn discriminative patterns from network-flow features."
    )
    cited_paragraph(
        doc,
        "However, the literature also shows that high benchmark accuracy alone is not enough. IDS models must be evaluated using precision, recall, F1-score, false positives, false negatives, multiclass attack-family behavior, and runtime cost [2], [5], [6]. This paper therefore evaluates a hybrid architecture using supervised ensemble learners and anomaly detection evidence on the UNSW-NB15 dataset."
    )

    doc.add_heading("2. Research Questions and Contributions", level=1)
    bullet(doc, "RQ1: Which evaluated model gives the strongest binary normal-versus-attack detection on UNSW-NB15?")
    bullet(doc, "RQ2: Does RF+XGBoost+Isolation Forest fusion improve over individual learners or simpler fusion?")
    bullet(doc, "RQ3: How do threshold policies affect false positives, false negatives, and F1-score?")
    bullet(doc, "RQ4: Which attack families remain difficult in multiclass classification?")
    bullet(doc, "RQ5: What inference-cost tradeoff is introduced by hybrid fusion?")

    doc.add_heading("3. Literature Review", level=1)
    doc.add_heading("3.1 Opening Gap Statement", level=2)
    cited_paragraph(
        doc,
        "Before recent developments in machine learning-based intrusion detection, network security research faced a persistent methodological problem: benchmark evaluations often reported high aggregate accuracy while giving limited attention to class imbalance, rare attack behavior, feature-selection stability, model interpretability, and deployment cost. The UNSW-NB15 dataset became an important response to this limitation because it provided a more modern representation of benign and malicious network traffic. However, the 2021 visualization-based analysis of UNSW-NB15 showed that the dataset itself requires careful exploratory understanding before modeling, since attack categories differ substantially in frequency and feature distribution [16]. This gap established the need for IDS studies that examine how model design, feature representation, and evaluation metrics affect real detection behavior."
    )

    doc.add_heading("3.2 Early Attempts", level=2)
    cited_paragraph(
        doc,
        "Early work attempted to address this problem by improving how classifiers and feature sets were matched to intrusion data. Zoghi and Serpen argued that ensemble classifier design must be tuned to dataset characteristics rather than selected only because an algorithm is popular [14]. Their work showed that models such as Random Forest and XGBoost can perform strongly on UNSW-NB15; however, it also implied that a single supervised ensemble may reflect the biases of a dataset split and may not fully capture rare or evolving attack patterns. Building on this concern, Yin et al. proposed IGRF-RFE as a hybrid feature-selection method for MLP-based intrusion detection [15]. Their study addressed dimensionality and feature relevance, yet it demonstrated that performance gains depend heavily on which features are retained and how well the selected subset generalizes across attack categories. Similarly, ensemble-learning research in IoT intrusion detection confirmed the value of combining classifiers, but left open the question of how anomaly-oriented evidence could complement supervised decisions [10]."
    )

    doc.add_heading("3.3 Evolution of the Field", level=2)
    cited_paragraph(
        doc,
        "In response to these limitations, later research shifted from basic classifier benchmarking toward feature optimization, explainability, and hybrid decision-making. The 2024 comparative work on explainable AI emphasized that model performance alone is insufficient unless prediction reasons can be interpreted [13]. This was important because IDS outputs must support security analysts who manage false alarms and missed attacks. In parallel, Varzaneh and Hosseini advanced the feature-selection discussion using improved equilibrium optimization for network intrusion detection [12]. Their contribution reinforced that model accuracy is closely tied to feature quality; however, optimization-based feature selection still does not fully resolve the challenge of detecting unusual or weakly represented attack behavior."
    )
    cited_paragraph(
        doc,
        "The 2025 literature expanded this direction by examining deep learning, stacked ensembles, explainable ensemble methods, negative selection, and IoT botnet detection. Farhan et al. showed that deep learning can improve network-based intrusion detection on UNSW-NB15, but such models may introduce computational overhead and reduced interpretability [6]. The stacked machine learning study on UNSW-NB15 and the xIDS-EnsembleGuard framework continued the ensemble trend, showing that model combination can improve robustness and explanation quality [9], [10]. However, these works also show that ensemble complexity must be justified by measurable improvement rather than assumed to be superior. Ali et al. extended the discussion to IoT botnet detection using stacked ensembles, demonstrating the relevance of ensemble learning in heterogeneous networks [7]. Li et al. contributed a different perspective by emphasizing anomaly-oriented detector generation from anomaly samples rather than purely supervised classification [8]."
    )

    doc.add_heading("3.4 Convergence Point", level=2)
    cited_paragraph(
        doc,
        "Recent studies from 2024 to 2026 collectively converge on a consistent conclusion: effective intrusion detection requires more than selecting the most accurate classifier. LiteShield argues for lightweight hybrid feature selection in resource-constrained networks, indicating that deployability and computational efficiency must be considered alongside detection accuracy [1]. Hossain et al. focus on generalization capability, reinforcing the concern that benchmark performance may not transfer to unseen traffic distributions [2]. Alhusseini et al. propose an AI-powered hybrid IDS for cloud security using metaheuristic optimization, reflecting the field's movement toward adaptive hybrid architectures [3]. Hussein and Repas further support this direction by combining deep autoencoder-based representation learning with XGBoost and Logistic Regression [4]. Finally, the rigorous supervised learning comparison on UNSW-NB15 demonstrates that classical models such as Random Forest, SVM, Decision Tree, and XGBoost remain highly competitive when evaluated with transparent preprocessing and validation [5]."
    )
    add_literature_table(doc)

    doc.add_heading("3.5 Motivation Bridge", level=2)
    cited_paragraph(
        doc,
        "The unresolved issue is how to combine strong tabular supervised learning with anomaly-sensitive evidence for suspicious traffic patterns that may not be fully represented in labeled training data. This gap motivates the design adopted in this paper: a hybrid supervised and anomaly detection architecture using Random Forest, XGBoost, and Isolation Forest on UNSW-NB15. Random Forest and XGBoost are selected because the literature consistently identifies tree-based ensemble learners as strong performers on structured intrusion data [5], [14]. Isolation Forest is included to provide anomaly-sensitive evidence that complements supervised attack probabilities. The fusion layer is therefore introduced as a controlled mechanism for examining whether supervised confidence and anomaly scores can jointly support more reliable intrusion detection under realistic evaluation metrics."
    )

    doc.add_heading("4. Methodology", level=1)
    doc.add_paragraph(
        "The methodology follows an empirical machine learning design. The official UNSW-NB15 training split is used for model fitting and internal validation, while the official testing split is reserved for final evaluation. The id field is removed because it is not a traffic behavior feature, and attack_cat is excluded from binary features to avoid label leakage. Numerical features are median-imputed and standardized. Categorical features are mode-imputed and one-hot encoded."
    )
    add_dataset_table(doc)
    doc.add_picture(str(CHART_DIR / "real_unsw_research_workflow.png"), width=Inches(6.1))
    caption(doc, "Figure 1. Hybrid IDS analysis workflow.")
    doc.add_paragraph(
        "The binary study evaluates Logistic Regression, Random Forest, XGBoost, Isolation Forest score-only detection, RF+XGBoost fusion, and RF+XGBoost+Isolation Forest fusion. The fusion layer is a logistic regression model trained on validation-set probability and anomaly-score meta-features. The multiclass study uses XGBoost for attack-family classification because XGBoost was the strongest binary learner and is suitable for structured tabular IDS data."
    )

    doc.add_heading("5. Experimental Results", level=1)
    add_table(doc, binary, ["Model", "Accuracy", "Precision", "Recall", "F1", "ROC AUC", "PR AUC", "False Positives", "False Negatives"], "Table 3. Binary model performance at threshold 0.50.")
    doc.add_paragraph(
        f"The binary results show that {best['Model']} gives the strongest default-threshold F1-score. The full hybrid does not outperform XGBoost, which is an important empirical finding because it prevents an overstated claim of hybrid superiority. A likely explanation is that XGBoost already captures most of the discriminative tabular structure in the official split, while Isolation Forest increases anomaly sensitivity but can also increase false positives."
    )
    doc.add_picture(str(CHART_DIR / "journal_ablation_f1.png"), width=Inches(5.9))
    caption(doc, "Figure 2. Ablation study showing binary F1-score at threshold 0.50.")

    add_table(doc, threshold, ["Model", "Policy", "Threshold", "Precision", "Recall", "F1", "False Positives", "False Negatives"], "Table 4. Threshold policy comparison.")
    doc.add_paragraph(
        "Threshold analysis shows that IDS performance is an operating-point decision. Recall-oriented thresholds reduce missed attacks but increase false positives. In this run, the default XGBoost threshold remained stronger on the official test split than the validation-selected F1 threshold, showing that threshold tuning itself can overfit the validation distribution."
    )
    doc.add_picture(str(CHART_DIR / "journal_threshold_policy.png"), width=Inches(5.9))
    caption(doc, "Figure 3. Threshold policy sensitivity.")

    add_table(doc, multiclass_summary, ["Model", "Accuracy", "Macro F1", "Weighted F1", "Milliseconds Per 1000 Records"], "Table 5. Multiclass XGBoost summary.")
    add_table(doc, multiclass_detail, ["Class", "Support", "Precision", "Recall", "F1"], "Table 6. Per-class multiclass performance.")
    doc.add_picture(str(CHART_DIR / "journal_multiclass_per_class_f1.png"), width=Inches(5.9))
    caption(doc, "Figure 4. Per-class multiclass F1-score.")

    add_table(doc, binary, ["Model", "Fit Time Seconds", "Predict Time Seconds", "Milliseconds Per 1000 Records"], "Table 7. Runtime and inference-cost comparison.")
    doc.add_picture(str(CHART_DIR / "journal_runtime.png"), width=Inches(5.9))
    caption(doc, "Figure 5. Binary inference cost by model.")

    doc.add_heading("6. Discussion", level=1)
    cited_paragraph(
        doc,
        "The results support a careful interpretation of hybrid IDS design. Hybrid fusion is useful as a mechanism for combining complementary evidence, but it is not automatically superior to a strong tree-boosting baseline. XGBoost provides the best default-threshold performance in the binary experiment, while the hybrid model provides a framework for studying how supervised confidence and anomaly evidence interact. This conclusion aligns with recent literature that emphasizes dataset-aware modeling, generalization, explainability, and deployability rather than accuracy alone [1], [2], [3], [4], [5], [6]."
    )
    cited_paragraph(
        doc,
        "The multiclass results show that binary detection is easier than attack-family identification. Frequent classes such as Normal and Generic are detected more reliably than rare classes such as Analysis, Backdoor, and DoS. This supports the literature's concern that IDS evaluation must include rare-class behavior and not rely only on aggregate accuracy [2], [8], [16]."
    )

    doc.add_heading("7. Threats to Validity", level=1)
    bullet(doc, "Dataset validity: UNSW-NB15 is a benchmark and may not fully represent current encrypted, cloud-native, or enterprise traffic.")
    bullet(doc, "Threshold validity: validation-selected thresholds may not generalize to the official test split or live network traffic.")
    bullet(doc, "Model validity: the study uses one dataset; stronger external validity would require CIC-IDS2017, BoT-IoT, ToN-IoT, or NF-UNSW-NB15.")
    bullet(doc, "Operational validity: runtime is measured offline and does not include streaming ingestion, SIEM integration, or analyst triage.")

    doc.add_heading("8. Conclusion", level=1)
    doc.add_paragraph(
        "This paper presented a hybrid supervised and anomaly-based intrusion detection study on the UNSW-NB15 dataset. The literature review shows that recent IDS research has moved from simple classifier benchmarking toward dataset-aware, interpretable, hybrid, and deployment-conscious models. The experiments show that XGBoost is the strongest default-threshold binary model in this implementation, while RF+XGBoost+Isolation Forest fusion provides a useful framework for analyzing complementary supervised and anomaly evidence. Future work should validate the architecture across additional datasets, add explainability methods such as SHAP, and evaluate streaming deployment conditions."
    )

    doc.add_section(WD_SECTION.NEW_PAGE)
    doc.add_heading("References", level=1)
    for idx, ref in enumerate(REFERENCES, start=1):
        paragraph = doc.add_paragraph()
        paper_file = CITATION_FILES.get(idx)
        if paper_file:
            add_hyperlink(paragraph, f"[{idx}] ", PAPER_DIR / paper_file)
        paragraph.add_run(ref)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUTPUT)
    print(f"Created {OUTPUT}")


if __name__ == "__main__":
    main()
