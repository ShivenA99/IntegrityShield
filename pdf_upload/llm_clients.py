"""
LLM Client implementations for OpenAI, Anthropic, and Google Gemini
Handles PDF upload and querying with proper error handling and fallbacks
"""
import asyncio
import aiohttp
import base64
import json
import ssl
from typing import Optional, Dict, List
from pathlib import Path
import time

# Try to import OpenAI SDK
try:
    from openai import AsyncOpenAI
    HAS_OPENAI_SDK = True
except ImportError:
    HAS_OPENAI_SDK = False

# Create SSL context that uses default certificates
# On macOS, this helps with certificate verification issues
try:
    import certifi
    ssl_context = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    # If certifi not available, use default context
    ssl_context = ssl.create_default_context()


class OpenAIClient:
    """OpenAI client for PDF upload and querying"""

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://api.openai.com/v1"
        self.file_id = None
        self.assistant_id = None
        self.vector_store_id = None

        # Initialize OpenAI SDK client if available
        if HAS_OPENAI_SDK:
            self.client = AsyncOpenAI(api_key=api_key)
        else:
            self.client = None
    
    async def upload_file(self, pdf_path: str) -> str:
        """Upload PDF to OpenAI - combined with query in query_with_file"""
        # For OpenAI, we combine upload and query, so this just returns the path
        # The actual upload happens in query_with_file
        return pdf_path
    
    async def query_with_file(self, file_id: str, prompt: str,
                             question_data: Optional[dict] = None) -> str:
        """
        Upload PDF and query OpenAI in one combined step.
        file_id is actually the pdf_path for OpenAI (we combine upload + query)
        """
        if not self.api_key:
            raise ValueError("OpenAI API key not provided")
        
        pdf_path = file_id  # For OpenAI, file_id is the pdf_path
        
        # Step 1: Upload file
        upload_url = f"{self.base_url}/files"
        upload_headers = {"Authorization": f"Bearer {self.api_key}"}
        
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        async with aiohttp.ClientSession(connector=connector) as session:
            # Upload PDF
            with open(pdf_path, 'rb') as f:
                data = aiohttp.FormData()
                data.add_field('file', f, filename=Path(pdf_path).name, 
                             content_type='application/pdf')
                data.add_field('purpose', 'user_data')
                
                async with session.post(upload_url, headers=upload_headers, data=data) as upload_response:
                    if upload_response.status != 200:
                        error_text = await upload_response.text()
                        raise Exception(f"OpenAI upload failed (status {upload_response.status}): {error_text}")
                    upload_result = await upload_response.json()
                    actual_file_id = upload_result['id']
            
            # Step 2: Wait for file processing
            file_status_url = f"{self.base_url}/files/{actual_file_id}"
            start_time = time.time()
            max_wait = 60
            
            while time.time() - start_time < max_wait:
                async with session.get(file_status_url, headers=upload_headers,
                                      timeout=aiohttp.ClientTimeout(total=10)) as status_response:
                    if status_response.status == 200:
                        status_result = await status_response.json()
                        file_status = status_result.get('status')
                        if file_status == 'processed':
                            break
                        elif file_status == 'error':
                            error_info = status_result.get('error', 'Unknown error')
                            raise Exception(f"File processing failed: {error_info}")
                await asyncio.sleep(2)
            else:
                raise Exception("File processing timeout")
            
            # Step 3: Query with the file (combined with upload)
            # Construct prompt
            full_prompt = prompt
            if question_data:
                full_prompt = f"{prompt}\n\nQuestion: {question_data.get('q', '')}"
            
            query_url = f"{self.base_url}/chat/completions"
            query_headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            # Correct format: content array with file and text as separate items
            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "file",
                                "file": {
                                    "file_id": actual_file_id
                                }
                            },
                            {
                                "type": "text",
                                "text": full_prompt
                            }
                        ]
                    }
                ]
            }
            
            async with session.post(query_url, headers=query_headers, json=payload,
                                   timeout=aiohttp.ClientTimeout(total=120)) as query_response:
                if query_response.status != 200:
                    error_text = await query_response.text()
                    raise Exception(f"OpenAI API error (status {query_response.status}): {error_text}")
                result = await query_response.json()
                if 'choices' in result and len(result['choices']) > 0:
                    return result['choices'][0]['message']['content']
                else:
                    raise Exception("Empty response from OpenAI")


class AnthropicClient:
    """Anthropic Claude client for PDF upload and querying using Files API"""
    
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://api.anthropic.com/v1"
        self.file_id = None
    
    async def upload_file(self, pdf_path: str) -> str:
        """Upload PDF to Anthropic Files API and return file_id"""
        if not self.api_key:
            raise ValueError("Anthropic API key not provided")
        
        url = f"{self.base_url}/files"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "files-api-2025-04-14"
        }
        
        try:
            with open(pdf_path, 'rb') as f:
                data = aiohttp.FormData()
                data.add_field('file', f, filename=Path(pdf_path).name, 
                             content_type='application/pdf')
                
                connector = aiohttp.TCPConnector(ssl=ssl_context)
                async with aiohttp.ClientSession(connector=connector) as session:
                    async with session.post(url, headers=headers, data=data,
                                           timeout=aiohttp.ClientTimeout(total=120)) as response:
                        if response.status != 200:
                            error_text = await response.text()
                            raise Exception(f"Anthropic file upload failed (status {response.status}): {error_text}")
                        result = await response.json()
                        file_id = result.get('id')
                        if not file_id:
                            raise Exception("No file_id returned from Anthropic upload")
                        self.file_id = file_id
                        return file_id
        except Exception as e:
            raise Exception(f"Failed to upload file to Anthropic: {str(e)}")
    
    async def query_with_file(self, file_id: str, prompt: str,
                             question_data: Optional[dict] = None) -> str:
        """Query Claude with file using Files API (file_id from upload)"""
        if not self.api_key:
            raise ValueError("Anthropic API key not provided")

        url = f"{self.base_url}/messages"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "files-api-2025-04-14",
            "content-type": "application/json"
        }

        # Construct prompt with question if provided
        full_prompt = prompt
        if question_data:
            full_prompt = f"{prompt}\n\nQuestion: {question_data.get('q', '')}"

        payload = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": [{
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": full_prompt
                    },
                    {
                        "type": "document",
                        "source": {
                            "type": "file",
                            "file_id": file_id
                        }
                    }
                ]
            }]
        }

        try:
            connector = aiohttp.TCPConnector(ssl=ssl_context)
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.post(url, headers=headers, json=payload,
                                       timeout=aiohttp.ClientTimeout(total=120)) as response:
                    if response.status == 429:
                        # Rate limit error - raise to trigger retry with backoff
                        error_text = await response.text()
                        raise Exception(f"Rate limit exceeded: {error_text}")
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(f"Anthropic API error (status {response.status}): {error_text}")
                    result = await response.json()
                    if 'content' in result and len(result['content']) > 0:
                        return result['content'][0]['text']
                    else:
                        raise Exception("Empty response from Anthropic")
        except asyncio.TimeoutError:
            raise Exception("Anthropic API request timed out")
        except Exception as e:
            raise Exception(f"Failed to query Anthropic: {str(e)}")


class GoogleClient:
    """Google Gemini client for PDF upload and querying"""
    
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"
        self.file_id = None
    
    async def upload_file(self, pdf_path: str) -> str:
        """Upload PDF to Google Gemini File API"""
        if not self.api_key:
            raise ValueError("Google API key not provided")

        url = f"{self.base_url}/files?key={self.api_key}"

        try:
            # Read file content
            with open(pdf_path, 'rb') as f:
                file_content = f.read()

            # Create multipart form data
            data = aiohttp.FormData()
            data.add_field('file',
                          file_content,
                          filename=Path(pdf_path).name,
                          content_type='application/pdf')

            connector = aiohttp.TCPConnector(ssl=ssl_context)
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.post(url, data=data,
                                       timeout=aiohttp.ClientTimeout(total=120)) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(f"Google upload failed (status {response.status}): {error_text}")
                    result = await response.json()
                    self.file_id = result['file']['name']

                    # Wait for file to be processed
                    await self._wait_for_file_processing()
                    return self.file_id
        except Exception as e:
            raise Exception(f"Failed to upload file to Google: {str(e)}")
    
    async def _wait_for_file_processing(self, max_wait: int = 60):
        """Wait for Google file to be processed"""
        url = f"{self.base_url}/{self.file_id}?key={self.api_key}"
        start_time = time.time()
        
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        while time.time() - start_time < max_wait:
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        result = await response.json()
                        if result.get('state') == 'ACTIVE':
                            return
            await asyncio.sleep(2)
        
        raise Exception("File processing timeout")
    
    async def query_with_file(self, file_id: str, prompt: str,
                             question_data: Optional[dict] = None) -> str:
        """Query Gemini with file"""
        if not self.api_key:
            raise ValueError("Google API key not provided")
        
        url = f"{self.base_url}/{self.model}:generateContent?key={self.api_key}"
        
        # Construct prompt with question if provided
        full_prompt = prompt
        if question_data:
            full_prompt = f"{prompt}\n\nQuestion: {question_data.get('q', '')}"
        
        payload = {
            "contents": [{
                "parts": [
                    {
                        "file_data": {
                            "file_uri": file_id,
                            "mime_type": "application/pdf"
                        }
                    },
                    {
                        "text": full_prompt
                    }
                ]
            }],
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 4096
            }
        }
        
        try:
            connector = aiohttp.TCPConnector(ssl=ssl_context)
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.post(url, json=payload,
                                       timeout=aiohttp.ClientTimeout(total=60)) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(f"Google API error: {error_text}")
                    result = await response.json()
                    if 'candidates' in result and len(result['candidates']) > 0:
                        return result['candidates'][0]['content']['parts'][0]['text']
                    else:
                        raise Exception("Empty response from Google")
        except asyncio.TimeoutError:
            raise Exception("Google API request timed out")
        except Exception as e:
            raise Exception(f"Failed to query Google: {str(e)}")

