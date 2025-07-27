#!/usr/bin/env python3
"""Setup script for Google Drive API credentials."""

import os
import sys
from pathlib import Path

def print_setup_instructions():
    """Print detailed setup instructions for Google Drive API."""
    
    print("="*60)
    print("GOOGLE DRIVE API SETUP INSTRUCTIONS")
    print("="*60)
    print()
    print("To automate PDF uploads to Google Drive, you need to set up API credentials.")
    print()
    print("STEP 1: Create Google Cloud Project")
    print("1. Go to https://console.cloud.google.com/")
    print("2. Click 'Select a project' → 'New Project'")
    print("3. Name your project (e.g., 'AI-Cheating-Detection')")
    print("4. Click 'Create'")
    print()
    print("STEP 2: Enable Google Drive API")
    print("1. In your project, go to 'APIs & Services' → 'Library'")
    print("2. Search for 'Google Drive API'")
    print("3. Click on it and click 'Enable'")
    print()
    print("STEP 3: Create Credentials")
    print("1. Go to 'APIs & Services' → 'Credentials'")
    print("2. Click 'Create Credentials' → 'OAuth 2.0 Client IDs'")
    print("3. Choose 'Desktop application'")
    print("4. Name it (e.g., 'AI Cheating Detection')")
    print("5. Click 'Create'")
    print()
    print("STEP 4: Download Credentials")
    print("1. Click the download button (⬇️) next to your OAuth 2.0 Client ID")
    print("2. Save the file as 'credentials.json'")
    print("3. Place 'credentials.json' in the backend directory")
    print()
    print("STEP 5: Install Required Packages")
    print("Run this command:")
    print("pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client")
    print()
    print("STEP 6: Test Setup")
    print("Run: python3 automated_google_drive_evaluation.py")
    print("The first time you run it, it will open a browser for authentication.")
    print()

def check_requirements():
    """Check if all requirements are met."""
    
    print("="*60)
    print("REQUIREMENTS CHECK")
    print("="*60)
    print()
    
    # Check Python packages
    try:
        import google.auth
        import google_auth_oauthlib
        import googleapiclient
        print("✅ Google Drive API packages installed")
    except ImportError:
        print("❌ Google Drive API packages missing")
        print("Install with: pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client")
        return False
    
    # Check credentials file
    if os.path.exists('credentials.json'):
        print("✅ credentials.json found")
    else:
        print("❌ credentials.json not found")
        print("Please download from Google Cloud Console")
        return False
    
    # Check OpenAI API key
    if os.getenv("OPENAI_API_KEY"):
        print("✅ OPENAI_API_KEY set")
    else:
        print("❌ OPENAI_API_KEY not set")
        print("Set with: export OPENAI_API_KEY=your_api_key")
        return False
    
    # Check PDF file
    pdf_path = Path("../attacked (7).pdf")
    if pdf_path.exists():
        print(f"✅ PDF file found: {pdf_path}")
    else:
        print(f"❌ PDF file not found: {pdf_path}")
        return False
    
    print()
    print("✅ All requirements met!")
    return True

def create_sample_credentials_template():
    """Create a sample credentials.json template."""
    
    template = {
        "installed": {
            "client_id": "YOUR_CLIENT_ID.apps.googleusercontent.com",
            "project_id": "your-project-id",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_secret": "YOUR_CLIENT_SECRET",
            "redirect_uris": ["http://localhost"]
        }
    }
    
    import json
    with open('credentials_template.json', 'w') as f:
        json.dump(template, f, indent=2)
    
    print("📄 Created credentials_template.json")
    print("Replace the placeholder values with your actual credentials")

def main():
    """Main setup function."""
    
    print("="*60)
    print("GOOGLE DRIVE API SETUP")
    print("="*60)
    print()
    
    # Print instructions
    print_setup_instructions()
    
    # Check requirements
    if check_requirements():
        print("🎉 Setup complete! You can now run the automated evaluation.")
        print()
        print("Next steps:")
        print("1. Run: python3 automated_google_drive_evaluation.py")
        print("2. Follow the browser authentication process")
        print("3. Your PDF will be automatically uploaded and evaluated")
    else:
        print("❌ Setup incomplete. Please follow the instructions above.")
        print()
        print("Would you like me to create a credentials template? (y/n)")
        response = input().lower()
        if response == 'y':
            create_sample_credentials_template()

if __name__ == "__main__":
    main() 