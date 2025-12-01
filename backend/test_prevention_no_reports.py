#!/usr/bin/env python3
"""
Test prevention mode WITHOUT auto-reports - just verify core pipeline works
"""
import sys
import time
from pathlib import Path
import requests

# API Configuration
API_URL = "http://localhost:8000/api"
TIMEOUT = 1800  # 30 minutes

# Test files - Statistics
SUBJECT = "Statistics"
BASE_PATH = Path("../Eacl_demo_papers") / SUBJECT
QUESTION_PDF = BASE_PATH / "qpaper.pdf"
ANSWER_PDF = BASE_PATH / "answerkey.pdf"
Q_TEX = BASE_PATH / "qpaper.tex"
ANS_TEX = BASE_PATH / "answerkey.tex"

def start_pipeline(q_pdf: Path, ans_pdf: Path, q_tex: Path, ans_tex: Path):
    """Start a prevention mode pipeline run WITHOUT auto-reports"""
    print(f"=" * 80)
    print(f"STARTING PREVENTION MODE TEST (NO AUTO-REPORTS) - {SUBJECT}")
    print("=" * 80)
    print(f"Question PDF: {q_pdf}")
    print(f"Answer PDF: {ans_pdf}")
    print()

    # Build multipart form data
    files = {
        "original_pdf": (q_pdf.name, open(q_pdf, "rb"), "application/pdf"),
        "answer_key_pdf": (ans_pdf.name, open(ans_pdf, "rb"), "application/pdf"),
        "manual_tex": (q_tex.name, open(q_tex, "rb"), "text/plain"),
        "manual_answer_tex": (ans_tex.name, open(ans_tex, "rb"), "text/plain"),
    }

    data = {
        "mode": "prevention",  # Use prevention mode
        "assessment_name": f"{SUBJECT}_Prevention_NoReports_Test",
        "target_stages": "all",
        "auto_vulnerability_report": "false",  # DISABLE auto-reports
        "auto_evaluation_reports": "false",    # DISABLE auto-reports
    }

    response = requests.post(f"{API_URL}/pipeline/start", files=files, data=data, timeout=60)

    if response.status_code not in [200, 202]:  # 202 = Accepted (async operation started)
        print(f"✗ Failed to start pipeline: {response.status_code}")
        print(response.text)
        sys.exit(1)

    result = response.json()
    run_id = result["run_id"]
    print(f"✓ Pipeline started successfully!")
    print(f"  Run ID: {run_id}")
    print(f"  Mode: prevention (no auto-reports)")
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
            response = requests.get(f"{API_URL}/pipeline/{run_id}/status", timeout=10)
            if response.status_code != 200:
                print(f"✗ Status check failed: {response.status_code}")
                time.sleep(5)
                continue

            data = response.json()
            status = data.get("status", "unknown")
            current_stage = data.get("current_stage")

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

def main():
    """Main test function"""
    # Check if files exist
    if not all([QUESTION_PDF.exists(), ANSWER_PDF.exists(), Q_TEX.exists(), ANS_TEX.exists()]):
        print("✗ Test files not found!")
        print(f"  Question PDF exists: {QUESTION_PDF.exists()}")
        print(f"  Answer PDF exists: {ANSWER_PDF.exists()}")
        print(f"  Q TEX exists: {Q_TEX.exists()}")
        print(f"  Ans TEX exists: {ANS_TEX.exists()}")
        sys.exit(1)

    # Check if server is running
    try:
        requests.get(f"{API_URL}/health", timeout=5)
    except requests.exceptions.RequestException:
        print("✗ Server not running! Please start the server first.")
        print("  Run: FAIRTESTAI_AUTO_APPLY_MIGRATIONS=false bash scripts/run_dev_server.sh")
        sys.exit(1)

    # Run test
    run_id = start_pipeline(QUESTION_PDF, ANSWER_PDF, Q_TEX, ANS_TEX)
    success = monitor_pipeline(run_id)

    if success:
        print()
        print("=" * 80)
        print(f"PREVENTION MODE (NO REPORTS) TEST COMPLETED SUCCESSFULLY! ✓")
        print(f"Run ID: {run_id}")
        print("=" * 80)
    else:
        print()
        print("=" * 80)
        print("PREVENTION MODE TEST FAILED ✗")
        print("=" * 80)
        sys.exit(1)

if __name__ == "__main__":
    main()
