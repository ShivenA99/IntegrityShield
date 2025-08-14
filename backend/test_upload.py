#!/usr/bin/env python3
"""Test PDF upload to Google Drive."""

import os
import sys
from pathlib import Path

# Add the app directory to the Python path
sys.path.insert(0, str(Path(__file__).parent / 'app'))

def test_pdf_upload():
    """Test uploading a PDF to Google Drive."""
    
    print("Testing PDF upload to Google Drive...")
    
    try:
        from app.services.openai_eval_service import GoogleDriveUploader
        
        # Create uploader
        uploader = GoogleDriveUploader()
        
        if not uploader.service:
            print("❌ Google Drive service not available")
            return False
        
        # Look for a test PDF file
        test_pdf = None
        possible_paths = [
            Path("../attacked (7).pdf"),
            Path("data/assessments/bb3fdb18-c528-43ce-b1c6-737c2e4e73dc/bb3fdb18-c528-43ce-b1c6-737c2e4e73dc.pdf"),
            Path("output/0200ed40-ed6a-4fad-a589-1284fea0c7ee_attacked.tex")
        ]
        
        for path in possible_paths:
            if path.exists():
                test_pdf = path
                break
        
        if not test_pdf:
            print("❌ No test PDF file found")
            print("   Looked in:")
            for path in possible_paths:
                print(f"   - {path}")
            return False
        
        print(f"✅ Found test file: {test_pdf}")
        
        # Try to upload
        print("📤 Uploading to Google Drive...")
        pdf_url = uploader.upload_pdf_to_drive(test_pdf)
        
        if pdf_url:
            print(f"✅ Upload successful!")
            print(f"   URL: {pdf_url}")
            return True
        else:
            print("❌ Upload failed")
            return False
            
    except Exception as e:
        print(f"❌ Error during upload test: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run the upload test."""
    print("="*60)
    print("GOOGLE DRIVE UPLOAD TEST")
    print("="*60)
    
    success = test_pdf_upload()
    
    print("\n" + "="*60)
    if success:
        print("🎉 UPLOAD TEST PASSED!")
        print("Your Google Drive integration is working correctly.")
    else:
        print("❌ UPLOAD TEST FAILED!")
        print("Check the error messages above for details.")

if __name__ == "__main__":
    main()
