#!/usr/bin/env python3
"""
Mock tests for LLM API calls to validate correct format usage.
These tests use mocks to avoid making actual API calls while verifying
that the correct API formats are used.
"""

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from flask import Flask
from app.config import BaseConfig

# Initialize Flask app for config access
app = Flask(__name__)
app.config.from_object(BaseConfig)


class MockResponse:
    """Mock response object for OpenAI Responses API."""
    
    def __init__(self, content: str, response_id: str = "resp_test_123"):
        self.id = response_id
        self.content = content
        self.choices = [MagicMock()]
        self.choices[0].message = MagicMock()
        self.choices[0].message.content = content


class TestGoldAnswerGeneration:
    """Test gold answer generation service with mocked API calls."""
    
    def test_build_prompt_format(self):
        """Test that _build_prompt uses correct input_text/input_image format."""
        print("\n=== Testing Gold Answer Prompt Format ===")
        
        with app.app_context():
            from app.services.pipeline.gold_answer_generation_service import GoldAnswerGenerationService
            
            service = GoldAnswerGenerationService()
            
            question = {
                "question_number": "1",
                "stem_text": "What is 2+2?",
                "question_type": "mcq_single",
                "options": {"A": "3", "B": "4", "C": "5"},
            }
            document = {}
            
            messages = service._build_prompt(question, document)
            
            errors = []
            for msg in messages:
                role = msg.get("role")
                content = msg.get("content", [])
                if not isinstance(content, list):
                    errors.append(f"Content in {role} message is not a list")
                    continue
                    
                for part in content:
                    part_type = part.get("type")
                    if part_type == "text":
                        errors.append(f"Found 'text' instead of 'input_text' in {role} message")
                    elif part_type == "image_url":
                        errors.append(f"Found 'image_url' instead of 'input_image' in {role} message")
                    elif part_type not in ("input_text", "input_image"):
                        errors.append(f"Unknown content type: {part_type} in {role} message")
            
            if errors:
                print("FAILED:")
                for error in errors:
                    print(f"  - {error}")
                return False
            
            # Verify structure
            system_msg = next((m for m in messages if m.get("role") == "system"), None)
            user_msg = next((m for m in messages if m.get("role") == "user"), None)
            
            if not system_msg or not user_msg:
                print("FAILED: Missing system or user message")
                return False
            
            print("PASSED: Gold answer prompt uses correct format (input_text/input_image)")
            return True
    
    async def test_call_model_async_format(self):
        """Test that _call_model_async uses correct Responses API format."""
        print("\n=== Testing Gold Answer API Call Format ===")
        
        with app.app_context():
            from app.services.pipeline.gold_answer_generation_service import GoldAnswerGenerationService
            
            service = GoldAnswerGenerationService()
            
            if not service.is_configured():
                print("SKIP: Service not configured (no API key)")
                return True
            
            question = {
                "question_number": "1",
                "stem_text": "What is 2+2?",
                "question_type": "mcq_single",
                "options": {"A": "3", "B": "4", "C": "5"},
            }
            
            messages = [
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": "System prompt"}],
                },
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": "User prompt"}],
                },
            ]
            
            # Mock the response
            mock_response = MagicMock()
            mock_response.id = "resp_test_123"
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message = MagicMock()
            mock_response.choices[0].message.content = '{"gold_answer": "B", "confidence": 0.9}'
            
            with patch.object(service._client.responses, 'create', new_callable=AsyncMock) as mock_create:
                mock_create.return_value = mock_response
                
                # Verify the call format
                result = await service._call_model_async(question, messages)
                
                # Check that create was called with correct format
                call_args = mock_create.call_args
                if call_args:
                    input_messages = call_args.kwargs.get("input") or call_args.args[1] if len(call_args.args) > 1 else None
                    
                    if input_messages:
                        errors = []
                        for msg in input_messages:
                            content = msg.get("content", [])
                            for part in content:
                                if part.get("type") == "text":
                                    errors.append("Found 'text' instead of 'input_text' in API call")
                                elif part.get("type") == "image_url":
                                    errors.append("Found 'image_url' instead of 'input_image' in API call")
                        
                        if errors:
                            print("FAILED:")
                            for error in errors:
                                print(f"  - {error}")
                            return False
                
                if result and result.get("gold_answer"):
                    print(f"PASSED: Gold answer API call successful (response_id: {mock_response.id})")
                    return True
                else:
                    print("FAILED: API call did not return expected result")
                    return False


class TestAnswerScoring:
    """Test answer scoring service with mocked API calls."""
    
    def test_score_answers_with_responses_format(self):
        """Test that _score_answers_with_responses uses correct format."""
        print("\n=== Testing Answer Scoring API Call Format ===")
        
        with app.app_context():
            from app.services.reports.answer_scoring import AnswerScoringService
            
            service = AnswerScoringService()
            
            if not service.enabled:
                print("SKIP: Service not enabled (no API key)")
                return True
            
            # Mock the response
            mock_response = MagicMock()
            mock_response.id = "resp_scoring_123"
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message = MagicMock()
            mock_response.choices[0].message.content = '{"scores": [{"provider": "openai", "score": 1.0, "verdict": "correct"}]}'
            
            with patch.object(service.client.responses, 'create', return_value=mock_response) as mock_create:
                provider_answers = [
                    {"provider": "openai", "answer_label": "B", "answer_text": "4"},
                ]
                
                try:
                    results = service._score_answers_with_responses(
                        question_text="What is 2+2?",
                        question_type="mcq_single",
                        gold_answer="B",
                        provider_answers=provider_answers,
                        options=[{"label": "A", "text": "3"}, {"label": "B", "text": "4"}],
                        detection_context=None,
                    )
                    
                    # Verify the call format
                    call_args = mock_create.call_args
                    if call_args:
                        input_messages = call_args.kwargs.get("input") or (call_args.args[1] if len(call_args.args) > 1 else None)
                        
                        if input_messages:
                            errors = []
                            for msg in input_messages:
                                content = msg.get("content", [])
                                for part in content:
                                    if part.get("type") == "text":
                                        errors.append("Found 'text' instead of 'input_text' in API call")
                            
                            if errors:
                                print("FAILED:")
                                for error in errors:
                                    print(f"  - {error}")
                                return False
                    
                    if results:
                        print(f"PASSED: Answer scoring API call successful (response_id: {mock_response.id}, providers: {len(provider_answers)})")
                        return True
                    else:
                        print("FAILED: API call did not return expected results")
                        return False
                        
                except Exception as exc:
                    print(f"FAILED: API call raised exception: {exc}")
                    return False


class TestGoogleGeminiClient:
    """Test Google Gemini client with mocked API calls."""
    
    async def test_query_with_file_format(self):
        """Test that query_with_file uses correct Gemini API format."""
        print("\n=== Testing Google Gemini API Call Format ===")
        
        with app.app_context():
            from app.services.reports.llm_clients import GoogleClient
            import aiohttp
            
            client = GoogleClient(
                api_key="test_key",
                model="models/gemini-1.5-pro"
            )
            
            question_bundle = {
                "provider": "google",
                "questions": [
                    {
                        "question_number": "1",
                        "question_text": "What is 2+2?",
                        "question_type": "mcq_single",
                        "options": [{"label": "A", "text": "3"}, {"label": "B", "text": "4"}],
                        "gold_answer": "B",
                    }
                ],
            }
            
            # Mock the aiohttp response
            mock_response_data = {
                "candidates": [{
                    "content": {
                        "parts": [{"text": '{"provider": "google", "answers": [{"question_number": "1", "answer_label": "B"}]}'}]
                    }
                }]
            }
            
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value=mock_response_data)
            mock_response.text = AsyncMock(return_value=json.dumps(mock_response_data))
            
            with patch('aiohttp.ClientSession.post', new_callable=AsyncMock) as mock_post:
                mock_post.return_value.__aenter__.return_value = mock_response
                
                try:
                    result = await client.query_with_file(
                        file_id="test_file_id",
                        prompt="Answer the questions",
                        question_data=question_bundle,
                    )
                    
                    # Verify the call was made
                    if mock_post.called:
                        call_args = mock_post.call_args
                        
                        # Check payload structure
                        if call_args and len(call_args.kwargs) > 0:
                            # aiohttp ClientSession.post uses 'json' parameter, not 'data'
                            payload = call_args.kwargs.get('json', {})
                            if not payload and 'data' in call_args.kwargs:
                                # Fallback: try to parse if data was passed as string
                                try:
                                    payload = json.loads(call_args.kwargs['data'])
                                except:
                                    payload = {}
                            
                            if payload:
                                contents = payload.get("contents", [])
                                if contents:
                                    first_content = contents[0]
                                    role = first_content.get("role")
                                    parts = first_content.get("parts", [])
                                    
                                    errors = []
                                    if role != "user":
                                        errors.append(f"Expected role 'user', got '{role}'")
                                    
                                    # Check that question bundle is in parts
                                    has_question_bundle = False
                                    for part in parts:
                                        if "text" in part:
                                            try:
                                                text_data = json.loads(part["text"])
                                                if "questions" in text_data or "provider" in text_data:
                                                    has_question_bundle = True
                                            except:
                                                pass
                                    
                                    if question_bundle and not has_question_bundle:
                                        errors.append("Question bundle not found in payload parts")
                                    
                                    if errors:
                                        print("FAILED:")
                                        for error in errors:
                                            print(f"  - {error}")
                                        return False
                                    
                                    print("PASSED: Google Gemini API call format correct (role: user, question_bundle included)")
                                    return True
                    
                    print("FAILED: API call was not made or payload structure incorrect")
                    return False
                    
                except Exception as exc:
                    print(f"FAILED: API call raised exception: {exc}")
                    import traceback
                    traceback.print_exc()
                    return False


class TestPDFOrchestrator:
    """Test PDF question orchestrator."""
    
    def test_build_batch_prompt(self):
        """Test that _build_batch_prompt returns question_bundle."""
        print("\n=== Testing PDF Orchestrator Question Bundle ===")
        
        with app.app_context():
            from app.services.reports.pdf_question_orchestrator import PDFQuestionEvaluator, QuestionPrompt
            
            questions = [
                QuestionPrompt(
                    question_id=1,
                    question_number="1",
                    question_text="What is 2+2?",
                    question_type="mcq_single",
                    options=[{"label": "A", "text": "3"}, {"label": "B", "text": "4"}],
                    gold_answer="B",
                )
            ]
            
            evaluator = PDFQuestionEvaluator(prompts=["dummy"])
            payload = evaluator._build_batch_prompt("google", questions)
            
            errors = []
            if "question_bundle" not in payload:
                errors.append("Missing 'question_bundle' in payload")
            if "prompt" not in payload:
                errors.append("Missing 'prompt' in payload")
            
            if payload.get("question_bundle"):
                qb = payload["question_bundle"]
                if "provider" not in qb:
                    errors.append("Question bundle missing 'provider'")
                if "questions" not in qb:
                    errors.append("Question bundle missing 'questions'")
            
            if errors:
                print("FAILED:")
                for error in errors:
                    print(f"  - {error}")
                return False
            
            print("PASSED: PDF orchestrator builds question bundle correctly")
            return True


async def run_all_tests():
    """Run all mock tests."""
    print("=" * 60)
    print("LLM API Call Mock Tests")
    print("=" * 60)
    
    results = []
    
    # Gold Answer Tests
    gold_tester = TestGoldAnswerGeneration()
    results.append(("Gold Answer Prompt Format", gold_tester.test_build_prompt_format()))
    results.append(("Gold Answer API Call Format", await gold_tester.test_call_model_async_format()))
    
    # Answer Scoring Tests
    scoring_tester = TestAnswerScoring()
    results.append(("Answer Scoring API Call Format", scoring_tester.test_score_answers_with_responses_format()))
    
    # Google Gemini Tests
    gemini_tester = TestGoogleGeminiClient()
    results.append(("Google Gemini API Call Format", await gemini_tester.test_query_with_file_format()))
    
    # PDF Orchestrator Tests
    orchestrator_tester = TestPDFOrchestrator()
    results.append(("PDF Orchestrator Question Bundle", orchestrator_tester.test_build_batch_prompt()))
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "PASS" if result else "SKIP/FAIL"
        print(f"{name}: {status}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n✓ All tests passed!")
        return 0
    else:
        print(f"\n✗ {total - passed} test(s) failed or skipped")
        return 1


def main():
    """Main entry point."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(run_all_tests())
    finally:
        loop.close()


if __name__ == "__main__":
    sys.exit(main())

