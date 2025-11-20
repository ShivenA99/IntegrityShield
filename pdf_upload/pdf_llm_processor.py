"""
PDF LLM Processor - Uploads PDF and queries single LLM
Main script that orchestrates PDF upload, LLM call, and report generation
"""
import asyncio
import argparse
import json
import os
import yaml
from pathlib import Path
from typing import Dict, List, Optional
import re
from datetime import datetime

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed, use system env vars

from llm_clients import OpenAIClient, AnthropicClient, GoogleClient
from report_generator import ReportGenerator


class PDFLLMProcessor:
    """Main processor for PDF upload and LLM querying"""
    
    def __init__(self, config_path: str = "config.yaml"):
        """Initialize processor with configuration"""
        self.config = self._load_config(config_path)
        self.clients = self._initialize_clients()
        self.report_gen = ReportGenerator()
        
    def _load_config(self, config_path: str) -> dict:
        """Load configuration from YAML file"""
        config_file = Path(config_path)
        if not config_file.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")
        
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
        
        # Replace environment variables
        for key, value in config['api_keys'].items():
            if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                env_var = value[2:-1]
                api_key = os.getenv(env_var, "")
                # Special handling for Google API key (check both GOOGLE_API_KEY and GOOGLE_AI_KEY)
                if key == 'google' and not api_key:
                    api_key = os.getenv("GOOGLE_AI_KEY", "")
                config['api_keys'][key] = api_key
        
        return config
    
    def _initialize_clients(self) -> dict:
        """Initialize Anthropic and OpenAI clients"""
        clients = {}
        
        # Initialize Anthropic
        try:
            api_key = self.config['api_keys'].get('anthropic')
            if api_key:
                clients['anthropic'] = AnthropicClient(
                    api_key=api_key,
                    model=self.config['models']['anthropic']
                )
                print("✓ Anthropic client initialized")
            else:
                print("⚠ Anthropic API key not found, skipping Anthropic")
        except Exception as e:
            print(f"⚠ Warning: Anthropic client initialization failed: {e}")
        
        # Initialize OpenAI
        try:
            api_key = self.config['api_keys'].get('openai')
            if api_key:
                clients['openai'] = OpenAIClient(
                    api_key=api_key,
                    model=self.config['models']['openai']
                )
                print("✓ OpenAI client initialized")
            else:
                print("⚠ OpenAI API key not found, skipping OpenAI")
        except Exception as e:
            print(f"⚠ Warning: OpenAI client initialization failed: {e}")
        
        if not clients:
            raise ValueError("No LLM clients could be initialized. Please check your API keys.")
        
        return clients
    
    async def upload_pdf(self, pdf_path: str) -> Dict[str, Optional[str]]:
        """
        Upload PDF to all available LLM providers in parallel
        Returns dict with file_ids for each provider
        """
        print(f"\n📤 Uploading PDF to LLM providers...")
        tasks = []
        provider_names = []
        
        if 'anthropic' in self.clients:
            tasks.append(self.clients['anthropic'].upload_file(pdf_path))
            provider_names.append('anthropic')
        if 'openai' in self.clients:
            tasks.append(self.clients['openai'].upload_file(pdf_path))
            provider_names.append('openai')
        
        if not tasks:
            raise ValueError("No clients available for PDF upload")
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        file_ids = {}
        for idx, provider in enumerate(provider_names):
            if isinstance(results[idx], Exception):
                print(f"❌ Error uploading to {provider}: {results[idx]}")
                file_ids[provider] = None
            else:
                print(f"✓ Successfully uploaded to {provider}")
                file_ids[provider] = results[idx]
        
        return file_ids
    
    async def query_llm(self, client_name: str, file_id: str, prompt: str) -> dict:
        """Query a specific LLM to answer all questions in the PDF"""
        if client_name not in self.clients or not file_id:
            return {
                "model_name": client_name.upper(),
                "prompt": prompt,
                "answer": None,
                "error": f"{client_name} client not available",
                "success": False
            }
        
        client = self.clients[client_name]
        
        # Build prompt asking to answer all questions in the document
        full_prompt = f"{prompt} in this document. Format your response as JSON with the following structure:\n{{\n  \"questions\": [\n    {{\"qid\": 1, \"q\": \"question text\", \"answer\": \"answer text\"}},\n    {{\"qid\": 2, \"q\": \"question text\", \"answer\": \"answer text\"}}\n  ]\n}}"
        
        max_retries = self.config['retry_settings']['max_retries']
        for attempt in range(max_retries):
            try:
                response = await client.query_with_file(
                    file_id=file_id,
                    prompt=full_prompt,
                    question_data=None
                )
                return {
                    "model_name": client_name.upper(),
                    "prompt": prompt,
                    "answer": response,
                    "success": True
                }
            except Exception as e:
                if attempt < max_retries - 1:
                    delay = self.config['retry_settings']['retry_delay'] * (attempt + 1)
                    print(f"⚠ Retry {attempt + 1}/{max_retries} for {client_name} after {delay}s...")
                    await asyncio.sleep(delay)
                    continue
                return {
                    "model_name": client_name.upper(),
                    "prompt": prompt,
                    "answer": None,
                    "error": str(e),
                    "success": False
                }
    
    def _parse_llm_response(self, answer_text: str) -> List[dict]:
        """Parse JSON response from LLM to extract questions and answers"""
        questions_list = []
        try:
            # Look for JSON block in the response
            json_match = re.search(r'\{[\s\S]*"questions"[\s\S]*\}', answer_text)
            if json_match:
                parsed = json.loads(json_match.group())
                questions_list = parsed.get('questions', [])
            else:
                # If no JSON found, treat entire response as answer to a single question
                questions_list = [{"qid": 1, "q": "All questions in the document", "answer": answer_text}]
        except Exception as e:
            print(f"   ⚠ Could not parse JSON from response: {e}")
            questions_list = [{"qid": 1, "q": "All questions in the document", "answer": answer_text}]
        return questions_list

    async def process_pdf(self, pdf_path: str) -> dict:
        """
        Main processing function:
        1. Upload PDF to all LLM providers (or prepare for combined upload+query)
        2. Ask each LLM to answer all questions in the PDF (in parallel)
        3. Parse and structure the responses
        """
        print(f"\n📄 Processing PDF: {pdf_path}")
        
        # Step 1: Upload PDF to all providers (or prepare file references)
        file_ids = await self.upload_pdf(pdf_path)
        
        available_providers = [name for name, fid in file_ids.items() if fid]
        if not available_providers:
            raise ValueError("No providers available after PDF upload")
        
        # Step 2: Make parallel calls to all LLMs
        # For OpenAI, file_id is actually the pdf_path (upload happens in query_with_file)
        prompt = self.config['prompt']
        print(f"\n🔄 Executing API calls (upload + query combined)...")
        print(f"   - Prompt: '{prompt}'")
        print(f"   - LLMs: {', '.join([p.capitalize() for p in available_providers])}")
        print(f"   - Asking LLMs to identify and answer all questions in the PDF\n")

        # Make parallel calls to all LLMs
        # For OpenAI, pass pdf_path directly; for others, use file_id
        tasks = []
        for provider in available_providers:
            if provider == 'openai':
                # OpenAI combines upload + query, so pass pdf_path
                tasks.append(self.query_llm(provider, pdf_path, prompt))
            else:
                # Other providers use file_id from upload
                tasks.append(self.query_llm(provider, file_ids[provider], prompt))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Show results
        all_questions_data = {}  # qid -> {q: text, answers: []}
        
        for idx, result in enumerate(results):
            provider = available_providers[idx]
            if isinstance(result, Exception):
                error_msg = str(result)
                print(f"   {provider.capitalize()}: ✗ Exception - {error_msg[:100]}")
                # Still try to add error to results for debugging
                continue
            
            if not result.get('success', False):
                error_msg = result.get('error', 'Unknown error')
                print(f"   {provider.capitalize()}: ✗ Failed - {error_msg[:100]}")
                # Log full error for debugging
                if len(error_msg) > 100:
                    print(f"      Full error: {error_msg}")
                continue
            
            print(f"   {provider.capitalize()}: ✓ Success")
            
            # Parse response
            answer_text = result.get('answer', '')
            if not answer_text:
                print(f"   {provider.capitalize()}: ⚠ Warning - Empty answer received")
                continue
                
            questions_list = self._parse_llm_response(answer_text)
            
            if not questions_list:
                print(f"   {provider.capitalize()}: ⚠ Warning - No questions parsed from response")
                print(f"      Response preview: {answer_text[:200]}...")
                continue
            
            print(f"   {provider.capitalize()}: Parsed {len(questions_list)} questions")
            
            # Merge into all_questions_data
            for q_data in questions_list:
                qid = q_data.get("qid", len(all_questions_data) + 1)
                q_text = q_data.get("q", "")
                
                if qid not in all_questions_data:
                    all_questions_data[qid] = {
                        "q": q_text,
                        "answers": []
                    }
                
                # Add answer from this LLM
                all_questions_data[qid]["answers"].append({
                    "model_name": result["model_name"],
                    "prompt": result["prompt"],
                    "answer": q_data.get("answer", ""),
                    "success": True
                })
        
        print()  # Empty line

        # Structure results
        structured_results = {
            "document": {
                "type": "document",
                "id": datetime.now().strftime("%Y%m%d_%H%M%S"),
                "asses_details": {
                    "sub": "",
                    "dom": ""
                }
            },
            "questions": {
                "type": "questions",
                "items": []
            }
        }

        # Add all questions with answers from all LLMs
        for qid, q_data in sorted(all_questions_data.items()):
            q_result = {
                "qid": qid,
                "q": q_data["q"],
                "answers": q_data["answers"]
            }
            structured_results["questions"]["items"].append(q_result)
        
        return structured_results
    
    
    def generate_report(self, results: dict, output_path: str = "report.txt"):
        """Generate formatted report"""
        print(f"\n📝 Generating report: {output_path}")
        self.report_gen.generate(results, output_path)
        print("✓ Report generated successfully")


async def main():
    """Main execution function"""
    parser = argparse.ArgumentParser(
        description="Process PDF files with a single LLM provider"
    )
    parser.add_argument(
        "pdf_filename",
        type=str,
        help="Name of the PDF file (must be in the input folder)"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="output",
        help="Output directory name (default: output)"
    )
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("PDF LLM Processor")
    print("=" * 80)
    
    try:
        processor = PDFLLMProcessor("config.yaml")
        
        # Find PDF in input folder
        input_folder = Path(processor.config['pdf_settings']['input_folder'])
        if not input_folder.exists():
            input_folder.mkdir(parents=True, exist_ok=True)
            print(f"\n📁 Created input folder: {input_folder}")
            print(f"   Please add PDF files to {input_folder.absolute()}")
            return
        
        # Look for the specified PDF file
        pdf_path = input_folder / args.pdf_filename
        
        # If not found with exact name, try case-insensitive search
        if not pdf_path.exists():
            pdf_files = list(input_folder.glob("*.pdf"))
            matching = [f for f in pdf_files if f.name.lower() == args.pdf_filename.lower()]
            if matching:
                pdf_path = matching[0]
            else:
                print(f"\n❌ PDF file '{args.pdf_filename}' not found in {input_folder}")
                print(f"   Available PDF files:")
                for pdf_file in pdf_files:
                    print(f"     - {pdf_file.name}")
                return
        
        print(f"\n📄 Processing PDF: {pdf_path.name}")
        
        # Create output folder structure
        output_base = Path(args.output_dir)
        output_base.mkdir(parents=True, exist_ok=True)
        
        # Create subfolder with PDF name (without extension) and timestamp
        pdf_name = pdf_path.stem  # filename without extension
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_folder = output_base / f"{pdf_name}_{timestamp}"
        output_folder.mkdir(parents=True, exist_ok=True)
        
        print(f"📁 Output folder: {output_folder.absolute()}")
        
        # Process PDF - LLM will identify and answer all questions in the document
        results = await processor.process_pdf(str(pdf_path))
        
        # Save JSON results in output folder
        output_json = output_folder / "results.json"
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\n💾 Results saved to: {output_json}")
        
        # Generate report in output folder
        report_path = output_folder / "report.txt"
        processor.generate_report(results, str(report_path))
        
        print("\n" + "=" * 80)
        print("✅ Processing complete!")
        print("=" * 80)
        print(f"   PDF: {pdf_path.name}")
        print(f"   Output folder: {output_folder.absolute()}")
        print(f"   Results: {output_json.name}")
        print(f"   Report: {report_path.name}")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())

