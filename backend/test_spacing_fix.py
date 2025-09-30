"""
Test the spacing fix by running a fresh pipeline execution.
This will use the same Quiz6.pdf and verify the spacing is now correct.
"""

import requests
import json
import time
from pathlib import Path

BASE_URL = "http://localhost:8001"
QUIZ_PDF = "backend/data/pipeline_runs/4bf3e702-6585-454a-add2-add388305ff1/Quiz6.pdf"

def test_spacing_fix():
    print("=" * 80)
    print("TESTING SPACING FIX")
    print("=" * 80)

    # Check that Quiz6.pdf exists
    quiz_path = Path(QUIZ_PDF)
    if not quiz_path.exists():
        print(f"❌ ERROR: Quiz6.pdf not found at {QUIZ_PDF}")
        return

    print(f"✓ Found Quiz6.pdf at {QUIZ_PDF}")
    print(f"  Size: {quiz_path.stat().st_size} bytes\n")

    # Step 1: Upload PDF
    print("Step 1: Uploading PDF...")
    with open(quiz_path, 'rb') as f:
        files = {'file': ('Quiz6.pdf', f, 'application/pdf')}
        response = requests.post(f"{BASE_URL}/api/documents/upload", files=files)

    if response.status_code != 200:
        print(f"❌ Upload failed: {response.status_code}")
        print(response.text)
        return

    data = response.json()
    run_id = data.get('run_id')
    print(f"✓ Upload successful, run_id: {run_id}\n")

    # Step 2: Process content discovery
    print("Step 2: Running content discovery...")
    response = requests.post(f"{BASE_URL}/api/pipeline/process-stage", json={
        "run_id": run_id,
        "stage": "content_discovery"
    })

    if response.status_code != 200:
        print(f"❌ Content discovery failed: {response.status_code}")
        return

    print("✓ Content discovery completed\n")

    # Step 3: Wait a moment for processing
    time.sleep(2)

    # Step 4: Get structured data
    print("Step 3: Fetching structured data...")
    response = requests.get(f"{BASE_URL}/api/questions/structured/{run_id}")

    if response.status_code != 200:
        print(f"❌ Failed to get structured data: {response.status_code}")
        return

    structured = response.json()
    questions = structured.get('questions', [])
    print(f"✓ Found {len(questions)} questions\n")

    # Step 5: Apply the same substitutions as before
    print("Step 4: Applying smart substitutions...")

    substitutions = {
        "1": {"original": "the", "replacement": "not", "start_pos": 8, "end_pos": 11},
        "2": {"original": "the", "replacement": "not", "start_pos": 9, "end_pos": 12},
        "3": {"original": "LSTM", "replacement": "CNN", "start_pos": 23, "end_pos": 27},
        "4": {"original": "LSTM", "replacement": "LSTMABCD", "start_pos": 14, "end_pos": 18},
        "5": {"original": "LSTMs", "replacement": "RNNs", "start_pos": 31, "end_pos": 36},
        "6": {"original": "RNNs", "replacement": "CNNs", "start_pos": 14, "end_pos": 18},
        "7": {"original": "bidirectional", "replacement": "unidirectional", "start_pos": 172, "end_pos": 185},
        "8": {"original": "RNN", "replacement": "c", "start_pos": 19, "end_pos": 22},
    }

    # Update questions with substitutions
    for q in questions:
        q_num = q.get('q_number')
        if q_num in substitutions:
            sub = substitutions[q_num]
            # Get bbox from positioning
            bbox = q.get('positioning', {}).get('bbox', [])

            if 'manipulation' not in q:
                q['manipulation'] = {}

            q['manipulation']['method'] = 'smart_substitution'
            q['manipulation']['substring_mappings'] = [{
                'id': f'test_{q_num}',
                'original': sub['original'],
                'replacement': sub['replacement'],
                'start_pos': sub['start_pos'],
                'end_pos': sub['end_pos'],
                'context': 'question_stem',
                'selection_page': 0,
                'selection_bbox': bbox if bbox else [0, 0, 100, 100]
            }]

    # Save updated structured data
    response = requests.post(f"{BASE_URL}/api/questions/save-structured/{run_id}", json=structured)

    if response.status_code != 200:
        print(f"❌ Failed to save structured data: {response.status_code}")
        return

    print("✓ Smart substitutions applied\n")

    # Step 6: Run PDF creation
    print("Step 5: Running PDF creation (with spacing fix)...")
    response = requests.post(f"{BASE_URL}/api/pipeline/process-stage", json={
        "run_id": run_id,
        "stage": "pdf_creation"
    })

    if response.status_code != 200:
        print(f"❌ PDF creation failed: {response.status_code}")
        print(response.text)
        return

    result = response.json()
    print("✓ PDF creation completed\n")

    # Step 7: Check the results
    print("=" * 80)
    print("VERIFICATION")
    print("=" * 80)

    run_dir = Path(f"backend/data/pipeline_runs/{run_id}")

    # Check if after_stream_rewrite.pdf exists
    rewrite_pdf = run_dir / "artifacts/stream_rewrite-overlay/after_stream_rewrite.pdf"
    if rewrite_pdf.exists():
        print(f"✓ after_stream_rewrite.pdf created: {rewrite_pdf.stat().st_size} bytes")
    else:
        print(f"⚠️  after_stream_rewrite.pdf not found")

    # Check debug output
    debug_json = run_dir / "artifacts/stream_rewrite-overlay/debug.pdf/after_reconstruction.json"
    if debug_json.exists():
        with open(debug_json, 'r') as f:
            debug_data = json.load(f)

        print(f"✓ Debug JSON found\n")
        print("Checking spacing values in TJ operators:")

        # Look for the spacing adjustment in operation 4 (for Q8)
        if 'operations' in debug_data:
            for op in debug_data['operations']:
                if op.get('operator') == 'TJ':
                    operands = op.get('operands', [])
                    if operands:
                        operand_str = operands[0]
                        # Check if it contains a large number (spacing adjustment)
                        if '1699' in operand_str or '1976' in operand_str:
                            print(f"  Found spacing value: {operand_str[:100]}...")
                            if operand_str.startswith('[1') or ', 1' in operand_str:
                                print(f"  ⚠️  STILL POSITIVE - Bug might not be fixed!")
                            elif operand_str.startswith('[-1') or ', -1' in operand_str:
                                print(f"  ✓ NEGATIVE - Bug is FIXED!")

    # Check final PDF
    final_pdf = run_dir / "artifacts/stream_rewrite-overlay/final.pdf"
    if final_pdf.exists():
        print(f"\n✓ final.pdf created: {final_pdf.stat().st_size} bytes")
        print(f"\nPlease manually inspect: {final_pdf}")
        print("Expected results:")
        print("  Q3: No extra space after 'CNN'")
        print("  Q5: No extra space after 'RNNs'")
        print("  Q7: Proper spacing around 'unidirectional'")
        print("  Q8: No overlap, 'c' properly positioned")

    print(f"\n✓ Test completed! Run ID: {run_id}")
    return run_id

if __name__ == "__main__":
    test_spacing_fix()
