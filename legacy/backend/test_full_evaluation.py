#!/usr/bin/env python3
"""Test the full evaluation workflow to debug where it's failing."""

import os
import sys
from pathlib import Path

# Add the app directory to the Python path
sys.path.insert(0, str(Path(__file__).parent / 'app'))

def test_openai_client():
    """Test OpenAI client creation."""
    print("Testing OpenAI client...")
    
    try:
        from openai import OpenAI
        
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("❌ OPENAI_API_KEY not set")
            return None
        
        client = OpenAI(api_key=api_key)
        print("✅ OpenAI client created successfully")
        return client
        
    except Exception as e:
        print(f"❌ Error creating OpenAI client: {e}")
        return None

def test_google_drive_upload():
    """Test Google Drive upload."""
    print("\nTesting Google Drive upload...")
    
    try:
        from app.services.openai_eval_service import GoogleDriveUploader
        
        uploader = GoogleDriveUploader()
        if not uploader.service:
            print("❌ Google Drive service not available")
            return None
        
        # Look for a PDF file instead of .tex
        test_file = Path("data/assessments/d6518618-365e-4f1f-84cf-84ca2ce64a72/attacked.pdf")
        if not test_file.exists():
            print(f"❌ Test PDF file not found: {test_file}")
            return None
        
        print(f"✅ Found test PDF file: {test_file}")
        
        # Upload to Google Drive
        pdf_url = uploader.upload_pdf_to_drive(test_file)
        if pdf_url:
            print(f"✅ Upload successful: {pdf_url}")
            return pdf_url
        else:
            print("❌ Upload failed")
            return None
            
    except Exception as e:
        print(f"❌ Error during upload: {e}")
        import traceback
        traceback.print_exc()
        return None

def test_openai_responses_api(client, pdf_url):
    """Test OpenAI Responses API."""
    print(f"\nTesting OpenAI Responses API with URL: {pdf_url}")
    
    try:
        # Test with a simple prompt
        prompt = "Answer the questions in this document"
        
        print(f"Testing with prompt: '{prompt}'")
        
        response = client.responses.create(
            model="gpt-4o-mini",
            input=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_file",
                            "file_url": pdf_url
                        },
                        {
                            "type": "input_text",
                            "text": prompt
                        }
                    ]
                }
            ]
        )
        
        print(f"✅ Response created successfully")
        print(f"   Status: {response.status}")
        
        if hasattr(response, 'output') and response.output:
            if hasattr(response.output[0], 'content') and response.output[0].content:
                answer_text = response.output[0].content[0].text.strip()
                print(f"   Answer preview: {answer_text[:100]}...")
            else:
                print(f"   Output structure: {response.output}")
        else:
            print(f"   No output in response")
        
        return response
        
    except Exception as e:
        print(f"❌ Error with OpenAI Responses API: {e}")
        import traceback
        traceback.print_exc()
        return None

def test_full_workflow():
    """Test the complete evaluation workflow."""
    print("="*60)
    print("FULL EVALUATION WORKFLOW TEST")
    print("="*60)
    
    # Step 1: Test OpenAI client
    client = test_openai_client()
    if not client:
        print("\n❌ Cannot proceed without OpenAI client")
        return False
    
    # Step 2: Test Google Drive upload
    pdf_url = test_google_drive_upload()
    if not pdf_url:
        print("\n❌ Cannot proceed without PDF URL")
        return False
    
    # Step 3: Test OpenAI Responses API
    response = test_openai_responses_api(client, pdf_url)
    if not response:
        print("\n❌ OpenAI Responses API failed")
        return False
    
    print("\n" + "="*60)
    print("🎉 ALL TESTS PASSED!")
    print("Your evaluation system should work correctly now.")
    return True

def main():
    """Run the full workflow test."""
    success = test_full_workflow()
    
    if not success:
        print("\n🔍 Troubleshooting tips:")
        print("- Check that OPENAI_API_KEY is set correctly")
        print("- Verify Google Drive credentials are working")
        print("- Check OpenAI API quota and billing")
        print("- Look at the error messages above for specific issues")

if __name__ == "__main__":
    main()
