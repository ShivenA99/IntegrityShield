# Demo Assets Structure

Place the demo-ready artifacts for each run (e.g., `paper_a`, `paper_b`, `paper_c`). Each run directory should contain:

```
input.pdf                   # original assessment
attacked.pdf                # AntiCheat PDF
vulnerability_report.csv    # overview table (AI,Correct,Incorrect,Total,Accuracy)
reference_report.csv        # overview table (same schema)
vulnerability_questions.json
reference_questions.json
```

The question JSON files should follow the schema outlined in `demo_assets/schema.md`, providing the stem, gold answer, and per-model evaluations for each numbered question. The demo backend automatically converts CSV rows into table data and will fall back to JSON if CSV files are absent.

Files with spaces in their names are supported, but keep the directory names concise (e.g., `paper_a`).
