#!/usr/bin/env python3
"""
Test detection mode with NLP paper from EACL demo dataset
"""
import sys
import time
from pathlib import Path
import requests

# API Configuration
API_URL = "http://localhost:5000/api"
TIMEOUT = 1800  # 30 minutes

# Test files
QUESTION_PDF = "../Eacl_demo_papers/NLP/qpaper.pdf"
ANSWER_PDF = "../Eacl_demo_papers/NLP/answerkey.pdf"
Q_TEX = "../Eacl_demo_papers/NLP/qpaper.tex"
ANS_TEX = "../Eacl_demo_papers/NLP/answerkey.tex"

def start_pipeline(q_pdf: Path, ans_pdf: Path, q_tex: Path, ans_tex: Path):
    """Start a detection mode pipeline run"""
    print(f"=" * 80)
    print("STARTING DETECTION MODE TEST - NLP PAPER")
    print("=" * 80)
    print(f"Question PDF: {q_pdf}")
    print(f"Answer PDF: {ans_pdf}")
    print()

    # Build multipart form data
    files = {
        "original_pdf": ("qpaper.pdf", open(q_pdf, "rb"), "application/pdf"),
        "answer_key_pdf": ("answerkey.pdf", open(ans_pdf, "rb"), "application/pdf"),
        "manual_tex": ("qpaper.tex", open(q_tex, "rb"), "text/plain"),
        "manual_answer_tex": ("answerkey.tex", open(ans_tex, "rb"), "text/plain"),
    }

    data = {
        "mode": "detection",  # Use detection mode
        "assessment_name": "NLP_Assessment_EACL_Demo"
    }

    response = requests.post(f"{API_URL}/pipeline/start", files=files, data=data, timeout=60)

    if response.status_code != 200:
        print(f"✗ Failed to start pipeline: {response.status_code}")
        print(response.text)
        sys.exit(1)

    result = response.json()
    run_id = result["run_id"]
    print(f"✓ Pipeline started successfully!")
    print(f"  Run ID: {run_id}")
    print()

    return run_id

def monitor_pipeline(run_id: str):
    """Monitor pipeline progress"""
    print("=" * 80)
    print("MONITORING PIPELINE PROGRESS")
    print("=" * 80)
    print()

    start_time = time.time()
    last_stage = None
    stage_start = time.time()

    while time.time() - start_time < TIMEOUT:
        try:
            response = requests.get(f"{API_URL}/pipeline/status/{run_id}", timeout=10)
            if response.status_code != 200:
                print(f"✗ Status check failed: {response.status_code}")
                time.sleep(5)
                continue

            data = response.json()
            status = data.get("status", "unknown")
            current_stage = data.get("current_stage")
            completed = data.get("completed_stages", [])

            # Print stage transitions
            if current_stage and current_stage != last_stage:
                if last_stage:
                    duration = time.time() - stage_start
                    print(f"  └─ Completed in {duration:.1f}s")
                    print()

                elapsed = int(time.time() - start_time)
                print(f"[{elapsed}s] Stage: {current_stage}")
                if status != "pending":
                    print(f"  Status: {status}")
                last_stage = current_stage
                stage_start = time.time()

            # Check if completed
            if status == "completed":
                if last_stage:
                    duration = time.time() - stage_start
                    print(f"  └─ Completed in {duration:.1f}s")
                print()
                print("✓ Pipeline completed successfully!")
                return True

            if status == "failed":
                print()
                print(f"✗ Pipeline failed: {data.get('error', 'Unknown error')}")
                return False

            time.sleep(2)

        except requests.exceptions.RequestException as e:
            print(f"✗ Connection error: {e}")
            time.sleep(5)
            continue

    print()
    print(f"✗ Timeout after {TIMEOUT}s")
    return False

def check_results(run_id: str):
    """Check generated results"""
    print()
    print("=" * 80)
    print("CHECKING RESULTS")
    print("=" * 80)

    response = requests.get(f"{API_URL}/pipeline/status/{run_id}", timeout=10)
    data = response.json()

    structured = data.get("structured_data", {})
    artifacts = structured.get("artifacts", {})

    print("\n📊 Generated Artifacts:")
    if artifacts:
        for method, files in artifacts.items():
            print(f"  • {method}:")
            for key, path in files.items():
                if path:
                    print(f"      - {key}: {Path(path).name}")
    else:
        print("  (none found)")

    reports = structured.get("reports", {})
    print("\n📈 Generated Reports:")
    if reports:
        for report_type, report_data in reports.items():
            print(f"  • {report_type}: {report_data.get('status', 'unknown')}")
    else:
        print("  (none found)")

    return True

def main():
    """Main test function"""
    # Check if files exist
    q_pdf = Path(QUESTION_PDF)
    ans_pdf = Path(ANSWER_PDF)
    q_tex = Path(Q_TEX)
    ans_tex = Path(ANS_TEX)

    if not all([q_pdf.exists(), ans_pdf.exists(), q_tex.exists(), ans_tex.exists()]):
        print("✗ Test files not found!")
        print(f"  Question PDF exists: {q_pdf.exists()}")
        print(f"  Answer PDF exists: {ans_pdf.exists()}")
        print(f"  Q TEX exists: {q_tex.exists()}")
        print(f"  Ans TEX exists: {ans_tex.exists()}")
        sys.exit(1)

    # Run test
    run_id = start_pipeline(q_pdf, ans_pdf, q_tex, ans_tex)
    success = monitor_pipeline(run_id)

    if success:
        check_results(run_id)
        print()
        print("=" * 80)
        print("TEST COMPLETED SUCCESSFULLY! ✓")
        print("=" * 80)
    else:
        print()
        print("=" * 80)
        print("TEST FAILED ✗")
        print("=" * 80)
        sys.exit(1)

if __name__ == "__main__":
    main()
