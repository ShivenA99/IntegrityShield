#!/usr/bin/env python3
"""Simple script to test with Google Drive link."""

import os

def generate_curl_command_with_your_link():
    """Generate curl command with your Google Drive link."""
    
    print("="*60)
    print("GOOGLE DRIVE TESTING")
    print("="*60)
    print()
    
    # Check for API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ OPENAI_API_KEY not set")
        print("Set it with: export OPENAI_API_KEY=your_api_key")
        print()
        return
    
    print("✅ OPENAI_API_KEY found")
    print()
    
    # Get your Google Drive link
    print("📋 STEP 1: Get your Google Drive link")
    print("1. Go to https://drive.google.com")
    print("2. Upload: ../attacked (7).pdf")
    print("3. Right-click → Share → Copy link")
    print("4. The link should look like:")
    print("   https://drive.google.com/file/d/1ABC123XYZ/view?usp=sharing")
    print()
    
    # Ask for the link
    print("📝 STEP 2: Enter your Google Drive link below")
    print("(Replace the example with your actual link)")
    print()
    
    # Example link - replace this with your actual link
    google_drive_link = "https://drive.google.com/file/d/1yjaFGcCa7SVEGDNhbe8jElVJ-UlwAi4K/view?usp=sharing"
    
    print(f"Current link: {google_drive_link}")
    print()
    print("🔧 STEP 3: Replace the link above with your actual Google Drive link")
    print()
    
    # Convert to direct download URL
    if "drive.google.com/file/d/" in google_drive_link:
        file_id = google_drive_link.split("/file/d/")[1].split("/")[0]
        direct_url = f"https://drive.google.com/uc?export=download&id={file_id}"
    else:
        direct_url = google_drive_link
    
    print("="*60)
    print("CURL COMMAND")
    print("="*60)
    print()
    
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
                        "file_url": "{direct_url}"
                    }},
                    {{
                        "type": "input_text",
                        "text": "Answer the questions"
                    }}
                ]
            }}
        ]
    }}' '''
    
    print(curl_command)
    print()
    
    print("="*60)
    print("INSTRUCTIONS")
    print("="*60)
    print()
    print("1. Replace 'YOUR_ACTUAL_FILE_ID' in the script with your real file ID")
    print("2. Run this script again to get the updated curl command")
    print("3. Copy and paste the curl command to test")
    print()
    print("Example:")
    print("If your link is: https://drive.google.com/file/d/1ABC123XYZ/view?usp=sharing")
    print("Then your file ID is: 1ABC123XYZ")
    print("Replace 'YOUR_ACTUAL_FILE_ID' with '1ABC123XYZ'")
    print()

if __name__ == "__main__":
    generate_curl_command_with_your_link() 