#!/usr/bin/env python3
"""
Comprehensive API test for re-run functionality.
Tests that mappings and data are correctly copied from original run.
"""

import requests
import json
import time
from pathlib import Path

BASE_URL = "http://localhost:8001"

def wait_for_stage_completion(run_id: str, stage_name: str, max_wait: int = 120):
    """Wait for a specific stage to complete."""
    print(f"⏳ Waiting for stage '{stage_name}' to complete...")
    start = time.time()

    while time.time() - start < max_wait:
        response = requests.get(f"{BASE_URL}/api/pipeline/{run_id}/status")
        if response.status_code != 200:
            print(f"❌ Failed to get status: {response.status_code}")
            return False

        data = response.json()
        stages = {s['name']: s for s in data.get('stages', [])}

        if stage_name in stages:
            stage_status = stages[stage_name]['status']
            print(f"   Stage '{stage_name}': {stage_status}")

            if stage_status == 'completed':
                print(f"✅ Stage '{stage_name}' completed!")
                return True
            elif stage_status == 'failed':
                print(f"❌ Stage '{stage_name}' failed!")
                return False

        time.sleep(2)

    print(f"⏰ Timeout waiting for stage '{stage_name}'")
    return False

def test_rerun(source_run_id: str):
    """Test re-run functionality with mapping preservation."""

    print("=" * 80)
    print("RE-RUN TEST")
    print("=" * 80)

    # Step 1: Get source run data
    print(f"\n📖 Step 1: Getting source run data ({source_run_id})...")
    response = requests.get(f"{BASE_URL}/api/pipeline/{source_run_id}/status")
    if response.status_code != 200:
        print(f"❌ Failed to get source run: {response.status_code}")
        return None

    source_data = response.json()
    source_structured = source_data.get('structured_data', {})
    source_manipulation = source_structured.get('manipulation_results', {})
    source_enhanced_pdfs = source_manipulation.get('enhanced_pdfs', {})

    print(f"✅ Source run found")
    print(f"   Status: {source_data['status']}")
    print(f"   Current stage: {source_data['current_stage']}")
    print(f"   Enhanced PDFs: {len(source_enhanced_pdfs)}")

    # Get source questions with mappings
    response = requests.get(f"{BASE_URL}/api/pipeline/{source_run_id}/questions")
    if response.status_code != 200:
        print(f"❌ Failed to get source questions")
        return None

    source_questions = response.json()
    questions_with_mappings = [q for q in source_questions
                               if q.get('substring_mappings') and len(q['substring_mappings']) > 0]

    print(f"   Questions: {len(source_questions)} total, {len(questions_with_mappings)} with mappings")

    # Step 2: Trigger re-run
    print(f"\n🔄 Step 2: Triggering re-run from source...")
    response = requests.post(f"{BASE_URL}/api/pipeline/rerun",
                            json={'source_run_id': source_run_id})

    if response.status_code != 200:
        print(f"❌ Failed to trigger re-run: {response.status_code}")
        print(response.text)
        return None

    result = response.json()
    new_run_id = result['run_id']
    print(f"✅ Re-run created with run_id: {new_run_id}")

    # Step 3: Verify initial state
    print(f"\n🔍 Step 3: Verifying re-run initial state...")
    time.sleep(1)  # Give backend time to hydrate

    response = requests.get(f"{BASE_URL}/api/pipeline/{new_run_id}/status")
    if response.status_code != 200:
        print(f"❌ Failed to get re-run status")
        return None

    rerun_data = response.json()
    print(f"✅ Re-run status retrieved")
    print(f"   Status: {rerun_data['status']}")
    print(f"   Current stage: {rerun_data['current_stage']}")
    print(f"   Expected: 'smart_substitution' (paused for user mapping)")

    # Step 4: Verify questions were copied
    print(f"\n📋 Step 4: Verifying questions were copied...")
    response = requests.get(f"{BASE_URL}/api/pipeline/{new_run_id}/questions")
    if response.status_code != 200:
        print(f"❌ Failed to get re-run questions")
        return None

    rerun_questions = response.json()
    print(f"✅ Questions verified: {len(rerun_questions)} questions")

    # Step 5: Check if mappings were preserved
    print(f"\n✏️ Step 5: Checking if mappings were preserved...")
    rerun_questions_with_mappings = [q for q in rerun_questions
                                     if q.get('substring_mappings') and len(q['substring_mappings']) > 0]

    print(f"   Source had: {len(questions_with_mappings)} questions with mappings")
    print(f"   Re-run has: {len(rerun_questions_with_mappings)} questions with mappings")

    if len(questions_with_mappings) > 0:
        # Compare first question with mappings
        source_q = next(q for q in source_questions if q.get('substring_mappings'))
        rerun_q = next(q for q in rerun_questions if q['question_number'] == source_q['question_number'])

        print(f"\n   Comparing Q{source_q['question_number']} mappings:")
        print(f"   Source mappings: {len(source_q.get('substring_mappings', []))}")
        print(f"   Re-run mappings: {len(rerun_q.get('substring_mappings', []))}")

        if source_q.get('substring_mappings'):
            source_mapping = source_q['substring_mappings'][0]
            rerun_mapping = rerun_q.get('substring_mappings', [{}])[0] if rerun_q.get('substring_mappings') else {}

            print(f"   Source: '{source_mapping.get('original', '')}' -> '{source_mapping.get('replacement', '')}'")
            print(f"   Re-run: '{rerun_mapping.get('original', '')}' -> '{rerun_mapping.get('replacement', '')}'")

            if source_mapping.get('original') == rerun_mapping.get('original'):
                print("   ✅ Mappings correctly preserved!")
            else:
                print("   ⚠️ Mappings differ between source and re-run")

    # Step 6: Advance to PDF creation
    print(f"\n📄 Step 6: Advancing re-run to pdf_creation...")
    response = requests.post(f"{BASE_URL}/api/pipeline/{new_run_id}/resume",
                            json={'stage': 'pdf_creation'})

    if response.status_code != 200:
        print(f"❌ Failed to start PDF creation: {response.status_code}")
        return None

    print("✅ Started PDF creation for re-run")

    # Step 7: Wait for completion
    print(f"\n🎨 Step 7: Waiting for PDF creation to complete...")
    if not wait_for_stage_completion(new_run_id, 'pdf_creation', max_wait=180):
        return None

    # Step 8: Verify final output
    print(f"\n📊 Step 8: Verifying final re-run output...")
    response = requests.get(f"{BASE_URL}/api/pipeline/{new_run_id}/status")
    if response.status_code != 200:
        print(f"❌ Failed to get final status")
        return None

    final_data = response.json()
    final_structured = final_data.get('structured_data', {})
    final_manipulation = final_structured.get('manipulation_results', {})
    final_enhanced_pdfs = final_manipulation.get('enhanced_pdfs', {})

    print(f"✅ Re-run completed")
    print(f"   Generated {len(final_enhanced_pdfs)} enhanced PDF(s)")

    for method, metadata in final_enhanced_pdfs.items():
        print(f"   - {method}:")
        print(f"     Path: {metadata.get('file_path', 'N/A')}")
        print(f"     Replacements: {metadata.get('replacements', 0)}")
        print(f"     Effectiveness: {metadata.get('effectiveness_score', 0):.2%}")

    # Step 9: Compare source vs re-run results
    print(f"\n⚖️ Step 9: Comparing source vs re-run results...")
    print(f"   Source PDFs: {len(source_enhanced_pdfs)}")
    print(f"   Re-run PDFs: {len(final_enhanced_pdfs)}")

    # Check if similar methods were used
    source_methods = set(source_enhanced_pdfs.keys())
    rerun_methods = set(final_enhanced_pdfs.keys())
    common_methods = source_methods & rerun_methods

    print(f"   Common methods: {common_methods}")

    for method in common_methods:
        source_meta = source_enhanced_pdfs[method]
        rerun_meta = final_enhanced_pdfs[method]

        source_replacements = source_meta.get('replacements', 0)
        rerun_replacements = rerun_meta.get('replacements', 0)

        print(f"   {method}:")
        print(f"     Source replacements: {source_replacements}")
        print(f"     Re-run replacements: {rerun_replacements}")

        if source_replacements == rerun_replacements:
            print(f"     ✅ Replacement count matches!")
        else:
            print(f"     ⚠️ Replacement count differs")

    print("\n" + "=" * 80)
    print(f"✅ RE-RUN TEST COMPLETED: {new_run_id}")
    print("=" * 80)

    return new_run_id

if __name__ == "__main__":
    # Try to load previous run ID
    source_run_id = None

    try:
        with open('/tmp/last_run_id.txt', 'r') as f:
            source_run_id = f.read().strip()
        print(f"📖 Loaded source run ID: {source_run_id}")
    except FileNotFoundError:
        print("⚠️ No previous run ID found. Please run test_fresh_run_api.py first.")
        print("Or provide a source_run_id as argument:")
        print("  python test_rerun_api.py <source_run_id>")
        import sys
        if len(sys.argv) > 1:
            source_run_id = sys.argv[1]

    if source_run_id:
        test_rerun(source_run_id)
    else:
        print("❌ No source run ID available")