#!/usr/bin/env python3
"""Test script to debug Google Drive service."""

import os
import sys
from pathlib import Path

# Add the app directory to the Python path
sys.path.insert(0, str(Path(__file__).parent / 'app'))

def test_google_drive_imports():
    """Test if Google Drive packages can be imported."""
    print("Testing Google Drive imports...")
    
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

def test_credentials_file():
    """Test if credentials.json is accessible."""
    print("\nTesting credentials file...")
    
    credentials_path = Path(__file__).parent / 'credentials.json'
    if credentials_path.exists():
        print(f"✅ credentials.json found at: {credentials_path}")
        
        # Check file size
        size = credentials_path.stat().st_size
        print(f"   File size: {size} bytes")
        
        # Try to read the file
        try:
            import json
            with open(credentials_path, 'r') as f:
                creds = json.load(f)
            print("✅ credentials.json is valid JSON")
            print(f"   Client ID: {creds['installed']['client_id'][:20]}...")
            return True
        except Exception as e:
            print(f"❌ Error reading credentials.json: {e}")
            return False
    else:
        print(f"❌ credentials.json not found at: {credentials_path}")
        return False

def test_google_drive_service():
    """Test Google Drive service initialization."""
    print("\nTesting Google Drive service...")
    
    try:
        from app.services.openai_eval_service import GoogleDriveUploader
        
        print("✅ GoogleDriveUploader class imported")
        
        # Try to create an instance
        uploader = GoogleDriveUploader()
        
        if uploader.service:
            print("✅ Google Drive service initialized successfully")
            return True
        else:
            print("❌ Google Drive service is None")
            return False
            
    except Exception as e:
        print(f"❌ Error testing Google Drive service: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_environment():
    """Test environment variables."""
    print("\nTesting environment...")
    
    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        print(f"✅ OPENAI_API_KEY is set ({openai_key[:10]}...)")
    else:
        print("❌ OPENAI_API_KEY not set")
    
    # Check current working directory
    print(f"   Current working directory: {os.getcwd()}")
    
    # Check if we're in the right place
    if Path("credentials.json").exists():
        print("✅ credentials.json is accessible from current directory")
    else:
        print("❌ credentials.json not accessible from current directory")

def main():
    """Run all tests."""
    print("="*60)
    print("GOOGLE DRIVE SERVICE DEBUG TEST")
    print("="*60)
    
    # Test imports
    imports_ok = test_google_drive_imports()
    
    # Test credentials
    credentials_ok = test_credentials_file()
    
    # Test environment
    test_environment()
    
    # Test service (only if imports and credentials are ok)
    if imports_ok and credentials_ok:
        service_ok = test_google_drive_service()
    else:
        service_ok = False
    
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print(f"Imports: {'✅ PASS' if imports_ok else '❌ FAIL'}")
    print(f"Credentials: {'✅ PASS' if credentials_ok else '❌ FAIL'}")
    print(f"Service: {'✅ PASS' if service_ok else '❌ FAIL'}")
    
    if not service_ok:
        print("\n🔍 Troubleshooting tips:")
        if not imports_ok:
            print("- Install missing packages: pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client")
        if not credentials_ok:
            print("- Check credentials.json file format and location")
        print("- Check the logs above for specific error messages")

if __name__ == "__main__":
    main()
