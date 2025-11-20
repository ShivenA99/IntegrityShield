"""
Simple test script to verify API calls work correctly
"""
import asyncio
import os
from dotenv import load_dotenv
from llm_clients import OpenAIClient, AnthropicClient

load_dotenv()

async def test_clients():
    print("Testing PDF upload module fixes...\n")

    # Test OpenAI
    print("1. Testing OpenAI client...")
    openai_client = OpenAIClient(
        api_key=os.getenv("OPENAI_API_KEY"),
        model="gpt-4o-mini"
    )

    try:
        file_id = await openai_client.upload_file("input/science_k-12_doc_01.pdf")
        print(f"   ✓ File uploaded: {file_id[:20]}...")

        response = await openai_client.query_with_file(
            file_id=file_id,
            prompt="What is the main topic of this document? Answer in one sentence.",
            question_data=None
        )
        print(f"   ✓ Query successful!")
        print(f"   Response: {response[:150]}...\n")
    except Exception as e:
        print(f"   ✗ Error: {e}\n")

    # Test Anthropic
    print("2. Testing Anthropic client...")
    anthropic_client = AnthropicClient(
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        model="claude-sonnet-4-5-20250929"
    )

    try:
        file_data = await anthropic_client.upload_file("input/science_k-12_doc_01.pdf")
        print(f"   ✓ File prepared (base64 encoded)")

        response = await anthropic_client.query_with_file(
            file_id=file_data,
            prompt="What is the main topic of this document? Answer in one sentence.",
            question_data=None
        )
        print(f"   ✓ Query successful!")
        print(f"   Response: {response[:150]}...\n")
    except Exception as e:
        print(f"   ✗ Error: {e}\n")

    print("✅ Testing complete!")

if __name__ == "__main__":
    asyncio.run(test_clients())
