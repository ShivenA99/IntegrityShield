#!/usr/bin/env python3
"""Test importing the openai_eval_service module."""

import sys
from pathlib import Path

# Add the app directory to the Python path
sys.path.insert(0, str(Path(__file__).parent / 'app'))

def test_import():
    """Test importing the module and check the flag."""
    print("Testing import of openai_eval_service...")
    
    try:
        # Import the module
        from app.services import openai_eval_service
        
        print("✅ Module imported successfully")
        
        # Check the flag
        if hasattr(openai_eval_service, 'GOOGLE_DRIVE_AVAILABLE'):
            flag_value = openai_eval_service.GOOGLE_DRIVE_AVAILABLE
            print(f"✅ GOOGLE_DRIVE_AVAILABLE = {flag_value}")
            
            if flag_value:
                print("🎉 Google Drive is available!")
            else:
                print("❌ Google Drive is NOT available")
        else:
            print("❌ GOOGLE_DRIVE_AVAILABLE flag not found")
        
        # Check if GoogleDriveUploader class is available
        if hasattr(openai_eval_service, 'GoogleDriveUploader'):
            print("✅ GoogleDriveUploader class is available")
        else:
            print("❌ GoogleDriveUploader class not found")
            
    except Exception as e:
        print(f"❌ Import failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

def test_google_drive_imports():
    """Test Google Drive imports directly."""
    print("\nTesting Google Drive imports directly...")
    
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
        print("✅ All Google Drive packages imported successfully")
        return True
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False

def main():
    """Run the import tests."""
    print("="*60)
    print("IMPORT TEST")
    print("="*60)
    
    # Test direct imports
    direct_imports_ok = test_google_drive_imports()
    
    # Test module import
    module_import_ok = test_import()
    
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print(f"Direct imports: {'✅ PASS' if direct_imports_ok else '❌ FAIL'}")
    print(f"Module import: {'✅ PASS' if module_import_ok else '❌ FAIL'}")
    
    if not module_import_ok:
        print("\n🔍 The issue is likely in the module import process.")
        print("This could be due to:")
        print("- Different Python environment")
        print("- Path issues")
        print("- Import order problems")

if __name__ == "__main__":
    main()
