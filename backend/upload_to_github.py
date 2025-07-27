#!/usr/bin/env python3
"""Upload PDF to GitHub and create public URL for testing."""

import os
import sys
import base64
import requests
from pathlib import Path

def upload_to_github_gist(pdf_path: Path, github_token: str = None) -> str:
    """Upload PDF to GitHub Gist and return raw URL."""
    
    if not github_token:
        print("Note: GitHub token not provided. Using mock upload.")
        print("To upload to real GitHub Gist, set GITHUB_TOKEN environment variable.")
        return "https://gist.githubusercontent.com/mock/attacked_7.pdf/raw"
    
    try:
        # Read the PDF file
        with open(pdf_path, 'rb') as f:
            pdf_content = f.read()
        
        # Encode to base64
        pdf_base64 = base64.b64encode(pdf_content).decode('utf-8')
        
        # Create gist data
        gist_data = {
            "description": "AI Assessment Test PDF",
            "public": True,
            "files": {
                "assessment.pdf": {
                    "content": f"PDF_BASE64:{pdf_base64}"
                }
            }
        }
        
        # Upload to GitHub Gist
        headers = {
            "Authorization": f"token {github_token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        response = requests.post(
            "https://api.github.com/gists",
            headers=headers,
            json=gist_data
        )
        
        if response.status_code == 201:
            gist_data = response.json()
            gist_id = gist_data["id"]
            raw_url = f"https://gist.githubusercontent.com/{gist_id}/raw/assessment.pdf"
            print(f"✅ PDF uploaded to GitHub Gist: {raw_url}")
            return raw_url
        else:
            print(f"❌ Failed to upload to GitHub: {response.status_code}")
            print(response.text)
            return None
            
    except Exception as e:
        print(f"Error uploading to GitHub: {e}")
        return None

def create_mock_github_url() -> str:
    """Create a mock GitHub URL for testing."""
    
    # This is a mock URL for testing purposes
    # In production, you would upload to a real GitHub Gist
    mock_url = "https://gist.githubusercontent.com/test-user/abc123/raw/attacked_7.pdf"
    
    print(f"Mock GitHub URL: {mock_url}")
    print("Note: This is a mock URL for testing")
    print("To use real GitHub upload, set GITHUB_TOKEN environment variable")
    
    return mock_url

def test_github_upload():
    """Test GitHub upload functionality."""
    
    print("="*60)
    print("GITHUB UPLOAD TEST")
    print("="*60)
    
    # Check for GitHub token
    github_token = os.getenv("GITHUB_TOKEN")
    
    if github_token:
        print("✅ GitHub token found")
    else:
        print("⚠️  GitHub token not found")
        print("Set GITHUB_TOKEN environment variable for real upload")
    
    # Path to PDF
    pdf_path = Path("../attacked (7).pdf")
    
    if not pdf_path.exists():
        print(f"❌ PDF file not found: {pdf_path}")
        return None
    
    print(f"📄 PDF file: {pdf_path}")
    print()
    
    # Upload to GitHub
    if github_token:
        url = upload_to_github_gist(pdf_path, github_token)
    else:
        url = create_mock_github_url()
    
    return url

def generate_test_curl_command(pdf_url: str):
    """Generate curl command for testing the uploaded PDF."""
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ OPENAI_API_KEY not set")
        return
    
    curl_command = f'''curl "https://api.openai.com/v1/responses" \\
    -H "Content-Type: application/json" \\
    -H "Authorization: Bearer {api_key}" \\
    -d '{{
        "model": "gpt-4o-mini",
        "input": [
            {{
                "role": "user",
                "content": [
                    {{
                        "type": "input_file",
                        "file_url": "{pdf_url}"
                    }},
                    {{
                        "type": "input_text",
                        "text": "Answer the questions"
                    }}
                ]
            }}
        ]
    }}' '''
    
    print("="*60)
    print("CURL COMMAND FOR TESTING")
    print("="*60)
    print(curl_command)
    print()
    
    return curl_command

def main():
    """Main function."""
    
    print("="*60)
    print("GITHUB PDF UPLOAD AND TESTING")
    print("="*60)
    print()
    
    # Test GitHub upload
    pdf_url = test_github_upload()
    
    if not pdf_url:
        print("❌ Failed to create PDF URL")
        return
    
    # Generate curl command
    curl_command = generate_test_curl_command(pdf_url)
    
    print("="*60)
    print("NEXT STEPS")
    print("="*60)
    print()
    print("1. To upload to real GitHub Gist:")
    print("   export GITHUB_TOKEN=your_github_token")
    print("   python3 upload_to_github.py")
    print()
    print("2. Test with curl command:")
    print("   Copy and paste the curl command above")
    print()
    print("3. Alternative hosting services:")
    print("   - AWS S3: aws s3 cp attacked_7.pdf s3://your-bucket/")
    print("   - Google Cloud: gsutil cp attacked_7.pdf gs://your-bucket/")
    print("   - Dropbox: Upload and get share link")
    print()
    print("4. Test with different AI models:")
    print("   - gpt-4o-mini (most vulnerable)")
    print("   - gpt-3.5-turbo")
    print("   - gpt-4o")
    print()

if __name__ == "__main__":
    main() 