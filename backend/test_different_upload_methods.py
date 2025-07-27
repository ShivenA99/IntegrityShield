#!/usr/bin/env python3
"""Test different methods of uploading PDFs to OpenAI to match ChatGPT behavior."""

import os
import sys
import base64
from pathlib import Path

# Add the backend directory to the Python path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

def test_method_1_files_api():
    """Test Method 1: Files API + Responses API (current method)"""
    print("="*60)
    print("METHOD 1: Files API + Responses API")
    print("="*60)
    
    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        # Upload PDF file
        pdf_path = Path("../reinforcement_learning.pdf")
        with open(pdf_path, "rb") as pdf_file:
            file_response = client.files.create(
                file=pdf_file,
                purpose="user_data"
            )
        
        file_id = file_response.id
        print(f"File uploaded with ID: {file_id}")
        
        # Use Responses API
        input_data = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_file",
                        "file_id": file_id
                    },
                    {
                        "type": "input_text",
                        "text": "Answer the questions"
                    }
                ]
            }
        ]

        response = client.responses.create(
            model="gpt-4o",
            input=input_data
        )
        
        # Extract answer
        if hasattr(response, 'output') and response.output:
            if hasattr(response.output[0], 'content') and response.output[0].content:
                answer_text = response.output[0].content[0].text.strip()
            else:
                answer_text = str(response.output[0])
        else:
            answer_text = str(response)
        
        print(f"Response: {answer_text}")
        
        # Cleanup
        client.files.delete(file_id)
        
    except Exception as e:
        print(f"Error: {e}")


def test_method_2_chat_completions_with_base64():
    """Test Method 2: Chat Completions with base64 encoded PDF"""
    print("\n" + "="*60)
    print("METHOD 2: Chat Completions with Base64 PDF")
    print("="*60)
    
    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        # Encode PDF to base64
        pdf_path = Path("../reinforcement_learning.pdf")
        with open(pdf_path, "rb") as pdf_file:
            pdf_data = pdf_file.read()
            base64_pdf = base64.b64encode(pdf_data).decode('utf-8')
        
        # Use Chat Completions with base64
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Answer the questions in this PDF"
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:application/pdf;base64,{base64_pdf}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=2000
        )
        
        answer_text = response.choices[0].message.content.strip()
        print(f"Response: {answer_text}")
        
    except Exception as e:
        print(f"Error: {e}")


def test_method_3_chat_completions_with_file_url():
    """Test Method 3: Chat Completions with file URL"""
    print("\n" + "="*60)
    print("METHOD 3: Chat Completions with File URL")
    print("="*60)
    
    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        # Upload file first
        pdf_path = Path("../reinforcement_learning.pdf")
        with open(pdf_path, "rb") as pdf_file:
            file_response = client.files.create(
                file=pdf_file,
                purpose="user_data"
            )
        
        file_id = file_response.id
        print(f"File uploaded with ID: {file_id}")
        
        # Use Chat Completions with file URL
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Answer the questions in this PDF"
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"https://api.openai.com/v1/files/{file_id}/content"
                            }
                        }
                    ]
                }
            ],
            max_tokens=2000
        )
        
        answer_text = response.choices[0].message.content.strip()
        print(f"Response: {answer_text}")
        
        # Cleanup
        client.files.delete(file_id)
        
    except Exception as e:
        print(f"Error: {e}")


def test_method_4_different_prompt():
    """Test Method 4: Different prompt variations"""
    print("\n" + "="*60)
    print("METHOD 4: Different Prompt Variations")
    print("="*60)
    
    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        # Upload PDF file
        pdf_path = Path("../reinforcement_learning.pdf")
        with open(pdf_path, "rb") as pdf_file:
            file_response = client.files.create(
                file=pdf_file,
                purpose="user_data"
            )
        
        file_id = file_response.id
        print(f"File uploaded with ID: {file_id}")
        
        # Test different prompts
        prompts = [
            "Answer the questions",
            "Please answer all the questions in this document",
            "Solve the quiz questions",
            "Provide answers to the questions in this PDF",
            "Follow the instructions and answer the questions"
        ]
        
        for i, prompt in enumerate(prompts, 1):
            print(f"\n--- Prompt {i}: '{prompt}' ---")
            
            input_data = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_file",
                            "file_id": file_id
                        },
                        {
                            "type": "input_text",
                            "text": prompt
                        }
                    ]
                }
            ]

            response = client.responses.create(
                model="gpt-4o",
                input=input_data
            )
            
            # Extract answer
            if hasattr(response, 'output') and response.output:
                if hasattr(response.output[0], 'content') and response.output[0].content:
                    answer_text = response.output[0].content[0].text.strip()
                else:
                    answer_text = str(response.output[0])
            else:
                answer_text = str(response)
            
            print(f"Response: {answer_text[:200]}...")
        
        # Cleanup
        client.files.delete(file_id)
        
    except Exception as e:
        print(f"Error: {e}")


def main():
    """Test all methods."""
    print("Testing different PDF upload methods to match ChatGPT behavior...")
    
    test_method_1_files_api()
    test_method_2_chat_completions_with_base64()
    test_method_3_chat_completions_with_file_url()
    test_method_4_different_prompt()


if __name__ == "__main__":
    main() 