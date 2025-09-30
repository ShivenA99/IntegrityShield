#!/usr/bin/env python3
"""
Comprehensive API test for fresh pipeline run.
Simulates complete UI interaction from upload to PDF generation.
"""

import requests
import json
import time
from pathlib import Path

BASE_URL = "http://localhost:8001"
TEST_PDF = "test_input_pdfs/Quiz6.pdf"

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

def test_fresh_run():
    """Test complete fresh run from upload to PDF generation."""

    print("=" * 80)
    print("FRESH RUN TEST")
    print("=" * 80)

    # Step 1: Upload PDF and start pipeline
    print("\n📤 Step 1: Uploading PDF and starting pipeline...")

    if not Path(TEST_PDF).exists():
        print(f"❌ Test PDF not found: {TEST_PDF}")
        return None

    with open(TEST_PDF, 'rb') as f:
        files = {'original_pdf': (Path(TEST_PDF).name, f, 'application/pdf')}
        data = {
            'target_stages': json.dumps(['smart_reading', 'content_discovery'])
        }

        response = requests.post(f"{BASE_URL}/api/pipeline/start", files=files, data=data)

    if response.status_code not in [200, 202]:
        print(f"❌ Failed to start pipeline: {response.status_code}")
        print(response.text)
        return None

    result = response.json()
    run_id = result['run_id']
    print(f"✅ Pipeline started with run_id: {run_id}")

    # Step 2: Wait for smart_reading to complete
    print("\n📖 Step 2: Waiting for smart_reading stage...")
    if not wait_for_stage_completion(run_id, 'smart_reading'):
        return None

    # Step 3: Wait for content_discovery to complete
    print("\n🎯 Step 3: Waiting for content_discovery stage...")
    if not wait_for_stage_completion(run_id, 'content_discovery'):
        return None

    # Step 4: Get questions
    print("\n📋 Step 4: Fetching discovered questions...")
    response = requests.get(f"{BASE_URL}/api/pipeline/{run_id}/questions")
    if response.status_code != 200:
        print(f"❌ Failed to get questions: {response.status_code}")
        return None

    questions = response.json()
    print(f"✅ Found {len(questions)} questions")
    for q in questions[:3]:
        print(f"   Q{q['question_number']}: {q.get('stem_text', '')[:60]}...")

    # Step 5: Manually advance to smart_substitution (user clicks button)
    print("\n🔄 Step 5: Advancing to smart_substitution stage (user clicks 'Continue')...")
    response = requests.post(f"{BASE_URL}/api/pipeline/{run_id}/resume",
                            json={'stage': 'smart_substitution'})
    if response.status_code != 200:
        print(f"❌ Failed to resume: {response.status_code}")
        return None
    print("✅ Advanced to smart_substitution stage")

    # Step 6: Add mappings to questions
    print("\n✏️ Step 6: Adding sample mappings to questions...")

    # Get first few questions and add simple mappings
    for i, question in enumerate(questions[:3]):
        q_num = question['question_number']
        stem_text = question.get('stem_text', '')

        # Find a simple word to replace (look for common words)
        sample_mapping = None
        for word in ['the', 'is', 'and', 'or', 'to']:
            if word in stem_text.lower():
                sample_mapping = {
                    'id': f'test_{i}',
                    'original': word,
                    'replacement': f'TEST{i}',
                    'start_pos': stem_text.lower().find(word),
                    'end_pos': stem_text.lower().find(word) + len(word),
                    'context': 'question_stem'
                }
                break

        if sample_mapping:
            # Update question with mapping
            update_data = {
                'substring_mappings': [sample_mapping]
            }

            response = requests.put(
                f"{BASE_URL}/api/questions/{run_id}/{q_num}",
                json=update_data
            )

            if response.status_code == 200:
                print(f"✅ Q{q_num}: Added mapping '{sample_mapping['original']}' -> '{sample_mapping['replacement']}'")
            else:
                print(f"⚠️ Q{q_num}: Failed to add mapping")

    # Step 7: Manually advance to pdf_creation (user clicks button)
    print("\n📄 Step 7: Advancing to pdf_creation stage (user clicks 'Create PDF')...")
    response = requests.post(f"{BASE_URL}/api/pipeline/{run_id}/resume",
                            json={'stage': 'pdf_creation'})
    if response.status_code != 200:
        print(f"❌ Failed to start PDF creation: {response.status_code}")
        return None
    print("✅ Started PDF creation")

    # Step 8: Wait for pdf_creation to complete
    print("\n🎨 Step 8: Waiting for PDF creation to complete...")
    if not wait_for_stage_completion(run_id, 'pdf_creation', max_wait=180):
        return None

    # Step 9: Get final status and check for generated PDFs
    print("\n📊 Step 9: Getting final results...")
    response = requests.get(f"{BASE_URL}/api/pipeline/{run_id}/status")
    if response.status_code != 200:
        print(f"❌ Failed to get final status")
        return None

    data = response.json()
    structured_data = data.get('structured_data', {})
    manipulation_results = structured_data.get('manipulation_results', {})
    enhanced_pdfs = manipulation_results.get('enhanced_pdfs', {})

    print(f"✅ Generated {len(enhanced_pdfs)} enhanced PDF(s)")
    for method, metadata in enhanced_pdfs.items():
        print(f"   - {method}: {metadata.get('file_path', 'N/A')}")
        print(f"     Replacements: {metadata.get('replacements', 0)}")
        print(f"     Effectiveness: {metadata.get('effectiveness_score', 0):.2%}")

    print("\n" + "=" * 80)
    print(f"✅ FRESH RUN COMPLETED SUCCESSFULLY: {run_id}")
    print("=" * 80)

    return run_id

if __name__ == "__main__":
    fresh_run_id = test_fresh_run()

    if fresh_run_id:
        print(f"\n💾 Saved run_id for re-run test: {fresh_run_id}")

        # Save run_id for re-run test
        with open('/tmp/last_run_id.txt', 'w') as f:
            f.write(fresh_run_id)