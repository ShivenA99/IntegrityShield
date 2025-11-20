#!/usr/bin/env python3
"""Test Google Gemini API integration with file upload."""

import asyncio
import json
import os
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from flask import Flask
from app.config import get_config

# Create Flask app context
app = Flask(__name__)
app.config.from_object(get_config("testing"))

async def test_gemini_file_upload():
    """Test Gemini file upload and query."""
    print("\n=== Testing Google Gemini API ===")
    
    with app.app_context():
        from app.services.reports.llm_clients import GoogleClient
        
        api_key = os.getenv("GOOGLE_AI_KEY")
        if not api_key:
            print("❌ GOOGLE_AI_KEY not set in environment")
            return False
        
        # Find a test PDF
        test_pdf = None
        for root, dirs, files in os.walk("data/pipeline_runs"):
            for file in files:
                if file.endswith(".pdf"):
                    test_pdf = os.path.join(root, file)
                    print(f"Found PDF: {test_pdf}")
                    break
            if test_pdf:
                break
        
        if not test_pdf:
            print("❌ No test PDF found. Looking for PDFs in data/pipeline_runs/")
            # Try to find any PDF in the project
            import glob
            pdfs = glob.glob("**/*.pdf", recursive=True)
            if pdfs:
                test_pdf = pdfs[0]
                print(f"Using PDF: {test_pdf}")
            else:
                return False
        
        print(f"✓ Found test PDF: {test_pdf}")
        
        client = GoogleClient(api_key=api_key, model="gemini-1.5-flash-latest")
        
        try:
            # Test file upload
            print("\n1. Testing file upload...")
            file_id = await client.upload_file(test_pdf)
            print(f"✓ File uploaded successfully. file_id: {file_id}")
            
            # Test query with file
            print("\n2. Testing query with file...")
            test_prompt = """You will analyze an attached PDF assessment and answer multiple questions.

REQUIRED JSON SCHEMA:
{
  "provider": "google",
  "answers": [
    {
      "question_number": "1",
      "answer_label": "B",
      "answer_text": "Ohm",
      "confidence": 0.95,
      "rationale": "Ohm is the unit of electrical resistance."
    }
  ]
}

Answer question 1 from the PDF. Return only valid JSON matching the schema above."""
            
            response = await client.query_with_file(file_id, test_prompt, question_data=None)
            print(f"✓ Query successful!")
            print(f"\nResponse (first 500 chars):\n{response[:500]}")
            
            # Try to parse as JSON
            try:
                extracted = response.strip()
                if extracted.startswith("```"):
                    first_newline = extracted.find("\n")
                    if first_newline != -1:
                        extracted = extracted[first_newline + 1 :]
                    closing = extracted.rfind("```")
                    if closing != -1:
                        extracted = extracted[:closing]
                parsed = json.loads(extracted.strip())
                print(f"\n✓ Response is valid JSON:")
                print(json.dumps(parsed, indent=2))
                return True
            except json.JSONDecodeError as e:
                print(f"\n⚠ Response is not valid JSON: {e}")
                print(f"Full response:\n{response}")
                return False
                
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()
            return False

if __name__ == "__main__":
    success = asyncio.run(test_gemini_file_upload())
    sys.exit(0 if success else 1)

