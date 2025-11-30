#!/usr/bin/env python3
"""
End-to-End test for Detection Flow
Tests that detection mode runs exactly 5 LaTeX methods and auto-generates reports
"""
import requests
import time
import json
from pathlib import Path

BASE_URL = "http://127.0.0.1:8000"
ORIGINAL_PDF = "data/pipeline_runs/245dd78d-7e81-4172-930c-b87ae00a9b32/Mathematics_K12_Assessment.pdf"
ANSWER_KEY_PDF = "data/pipeline_runs/245dd78d-7e81-4172-930c-b87ae00a9b32/answer_key_math_answer_key_final.pdf"

def start_detection_pipeline():
    """Start a new pipeline in detection mode"""
    print("=" * 80)
    print("STARTING DETECTION MODE PIPELINE")
    print("=" * 80)
    print(f"Original PDF: {ORIGINAL_PDF}")
    print(f"Answer Key: {ANSWER_KEY_PDF}")
    print()

    # Prepare files
    files = {
        "original_pdf": open(ORIGINAL_PDF, "rb"),
        "answer_key_pdf": open(ANSWER_KEY_PDF, "rb"),
    }

    # Note: For multi-value form fields like target_stages, we need to add each value separately
    data = {
        "assessment_name": "DetectionFlowE2ETest",
        "mode": "detection",
        "skip_if_exists": "false",  # Run all stages, don't skip
        "parallel_processing": "true",
    }

    # Add target_stages as separate form entries (required for Flask's getlist())
    target_stages_list = [
        ("target_stages", "smart_reading"),
        ("target_stages", "content_discovery"),
        ("target_stages", "smart_substitution"),
        ("target_stages", "effectiveness_testing"),
        ("target_stages", "document_enhancement"),
        ("target_stages", "pdf_creation"),
        ("target_stages", "results_generation"),
    ]

    try:
        # Combine data dict with target_stages list
        all_data = list(data.items()) + target_stages_list
        response = requests.post(f"{BASE_URL}/api/pipeline/start", files=files, data=all_data)
        response.raise_for_status()
        result = response.json()
        run_id = result["run_id"]
        print(f"✓ Pipeline started successfully!")
        print(f"  Run ID: {run_id}")
        print()
        return run_id
    except Exception as e:
        print(f"✗ Failed to start pipeline: {e}")
        if hasattr(e, 'response') and e.response:
            print(f"  Response: {e.response.text}")
        raise
    finally:
        for f in files.values():
            f.close()

def get_status(run_id):
    """Get current pipeline status"""
    try:
        response = requests.get(f"{BASE_URL}/api/pipeline/{run_id}/status")
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"✗ Failed to get status: {e}")
        return None

def monitor_pipeline(run_id, max_wait_seconds=600):
    """Monitor pipeline progress stage by stage"""
    print("=" * 80)
    print("MONITORING PIPELINE PROGRESS")
    print("=" * 80)

    start_time = time.time()
    last_stage = None
    last_status = None

    stage_timing = {}

    while True:
        elapsed = time.time() - start_time
        if elapsed > max_wait_seconds:
            print(f"\n✗ Timeout after {max_wait_seconds}s")
            break

        status = get_status(run_id)
        if not status:
            time.sleep(2)
            continue

        current_stage = status.get("current_stage")
        current_status = status.get("status")

        # Detect stage change
        if current_stage != last_stage:
            if last_stage:
                stage_timing[last_stage] = time.time() - stage_timing.get(f"{last_stage}_start", start_time)
                print(f"  └─ Completed in {stage_timing[last_stage]:.1f}s")

            if current_stage:
                stage_timing[f"{current_stage}_start"] = time.time()
                print(f"\n[{elapsed:.0f}s] Stage: {current_stage}")

            last_stage = current_stage

        # Detect status change
        if current_status != last_status:
            print(f"  Status: {current_status}")
            last_status = current_status

        # Check if done
        if current_status in ["completed", "failed"]:
            print(f"\n{'='*80}")
            print(f"PIPELINE {current_status.upper()} in {elapsed:.1f}s")
            print(f"{'='*80}")

            # Print stage timings
            print("\nStage Timings:")
            for stage, duration in stage_timing.items():
                if not stage.endswith("_start"):
                    print(f"  {stage}: {duration:.1f}s")

            return status

        time.sleep(3)

    return None

def verify_results(run_id):
    """Verify that detection flow produced correct outputs"""
    print("\n" + "=" * 80)
    print("VERIFYING RESULTS")
    print("=" * 80)

    status = get_status(run_id)
    if not status:
        print("✗ Could not get final status")
        return False

    # Check enhancement methods
    print("\n1. Checking enhancement methods...")
    methods = status.get("structured_data", {}).get("manipulation_results", {}).get("enhanced_pdfs", {})
    expected_methods = [
        "latex_icw",
        "latex_font_attack",
        "latex_dual_layer",
        "latex_icw_font_attack",
        "latex_icw_dual_layer"
    ]

    actual_methods = list(methods.keys())
    print(f"   Expected: {expected_methods}")
    print(f"   Actual: {actual_methods}")

    if set(actual_methods) == set(expected_methods):
        print("   ✓ Correct 5 LaTeX methods")
    else:
        print("   ✗ Methods mismatch!")
        return False

    # Check that pymupdf_overlay is NOT present
    if "pymupdf_overlay" in actual_methods:
        print("   ✗ pymupdf_overlay should NOT be in detection mode!")
        return False
    else:
        print("   ✓ pymupdf_overlay correctly excluded")

    # Check for enhanced PDFs
    print("\n2. Checking enhanced PDFs...")
    pdf_count = 0
    for method, data in methods.items():
        if data.get("file_path") or data.get("path"):
            pdf_path = data.get("file_path") or data.get("path")
            pdf_count += 1
            print(f"   ✓ {method}: {Path(pdf_path).name}")

    if pdf_count == 5:
        print(f"   ✓ All 5 enhanced PDFs generated")
    else:
        print(f"   ✗ Expected 5 PDFs, got {pdf_count}")
        return False

    # Check reports
    print("\n3. Checking auto-generated reports...")
    reports = status.get("structured_data", {}).get("reports", {})

    # Vulnerability report
    if reports.get("vulnerability_report"):
        print("   ✓ Vulnerability report generated")
    else:
        print("   ✗ Vulnerability report missing")
        return False

    # Detection report
    if reports.get("detection_report"):
        print("   ✓ Detection report generated")
    else:
        print("   ✗ Detection report missing")
        return False

    # Evaluation reports (should be 5, one per method)
    eval_reports = reports.get("evaluation_reports", {})
    print(f"   Found {len(eval_reports)} evaluation reports")
    for method in expected_methods:
        if method in eval_reports:
            print(f"   ✓ {method} evaluation report")
        else:
            print(f"   ✗ {method} evaluation report missing")
            return False

    print("\n" + "=" * 80)
    print("✓ ALL VERIFICATION CHECKS PASSED!")
    print("=" * 80)
    return True

if __name__ == "__main__":
    try:
        # Start pipeline
        run_id = start_detection_pipeline()

        # Monitor progress
        final_status = monitor_pipeline(run_id, max_wait_seconds=600)

        if not final_status:
            print("\n✗ Pipeline did not complete in time")
            exit(1)

        if final_status.get("status") == "failed":
            print(f"\n✗ Pipeline failed:")
            print(json.dumps(final_status.get("error_details"), indent=2))
            exit(1)

        # Verify results
        if verify_results(run_id):
            print(f"\n✓ Detection flow test PASSED!")
            print(f"  Run ID: {run_id}")
            exit(0)
        else:
            print(f"\n✗ Detection flow test FAILED!")
            exit(1)

    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        exit(130)
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
