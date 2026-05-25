# How to Run the Hybrid IDS Research Project

This guide explains how to run the research notebook, regenerate the Word document, charts, metrics, and execute the standalone analysis script.

## 1. Project Contents

- `research_methodology_explanation.docx` - academic research explanation document.
- `notebooks/hybrid_ids_research_analysis.ipynb` - executable research notebook with visible outputs.
- `scripts/run_hybrid_ids_analysis.py` - standalone Python analysis pipeline.
- `scripts/generate_research_deliverables.py` - regenerates charts, metrics, document, notebook, and ZIP.
- `charts/` - workflow, architecture, ROC, PR, confusion matrix, feature importance, and comparison charts.
- `metrics/` - metrics in CSV and JSON format.
- `data/sample_unsw_nb15_like.csv` - runnable sample dataset for demonstration.
- `requirements.txt` - Python package dependencies.
- `hybrid_ids_research_project.zip` - packaged deliverable archive.

## 2. Install Dependencies

Open PowerShell in the project folder:

```powershell
cd C:\Users\sambhram.u\Desktop\Research
python -m pip install -r requirements.txt
```

## 3. Run the Jupyter Notebook

Start Jupyter:

```powershell
jupyter notebook
```

Then open:

```text
notebooks/hybrid_ids_research_analysis.ipynb
```

Run all cells from top to bottom. The notebook is designed to execute without manual fixes. If UNSW-NB15 CSV files are not available, it uses the included sample dataset so charts and metrics still render.

## 4. Use Real UNSW-NB15 CSV Files

Place the UNSW-NB15 CSV files inside:

```text
data/
```

The notebook and standalone script automatically load all `.csv` files in the `data/` folder. The expected target column is:

```text
label
```

If available, the attack category column should be:

```text
attack_cat
```

## 5. Run the Standalone Analysis Script

From the project folder:

```powershell
python scripts\run_hybrid_ids_analysis.py
```

This trains Logistic Regression, Random Forest, XGBoost, and the hybrid fusion model, then prints the model comparison metrics.

## 6. Regenerate All Deliverables

To recreate the Word document, notebook template, charts, metrics, sample data, and ZIP package:

```powershell
python scripts\generate_research_deliverables.py
```

Generated outputs include:

- `research_methodology_explanation.docx`
- `notebooks/hybrid_ids_research_analysis.ipynb`
- `metrics/model_metrics.csv`
- `metrics/model_metrics.json`
- `charts/*.png`
- `hybrid_ids_research_project.zip`

## 7. Expected Output

After running the project successfully, you should see:

- Model comparison metrics for Logistic Regression, Random Forest, XGBoost, and Hybrid RF + XGBoost + Isolation Forest.
- Confusion matrix chart.
- ROC curve.
- Precision-recall curve.
- Feature importance chart.
- Model comparison bar chart.
- Research-ready Word document and notebook.

## 8. Notes

- The included sample dataset is for execution and presentation testing only.
- For final academic reporting, replace or supplement it with the official UNSW-NB15 CSV files.
- The hybrid model uses Random Forest probability, XGBoost probability, and Isolation Forest anomaly score as fusion-layer inputs.
