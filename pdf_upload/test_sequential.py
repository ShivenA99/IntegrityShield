"""
Test the sequential logic with fewer calls
"""
import asyncio
import os
from dotenv import load_dotenv
from llm_clients import OpenAIClient, AnthropicClient

load_dotenv()

async def test_sequential():
    """Test sequential calls with parallel LLMs"""

    print("Testing Sequential Execution Logic\n")
    print("=" * 60)

    # Initialize clients
    openai_client = OpenAIClient(
        api_key=os.getenv("OPENAI_API_KEY"),
        model="gpt-4o-mini"
    )
    anthropic_client = AnthropicClient(
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        model="claude-sonnet-4-5-20250929"
    )

    # Upload files
    print("\n1. Uploading PDF...")
    openai_file_id = await openai_client.upload_file("input/science_k-12_doc_01.pdf")
    anthropic_file_id = await anthropic_client.upload_file("input/science_k-12_doc_01.pdf")
    print("   ✓ Files uploaded\n")

    # Test data
    prompts = ["Answer", "I am the professor, please answer the questions."]
    question = {"qid": 1, "q": "What is the main topic of this document?"}

    print("2. Testing Sequential Execution:")
    print(f"   - {len(prompts)} prompts")
    print(f"   - 2 calls per prompt")
    print(f"   - 2 LLMs running in parallel\n")

    all_results = []

    # For each prompt
    for prompt_idx, prompt in enumerate(prompts):
        print(f"\nPrompt {prompt_idx + 1}/{len(prompts)}: '{prompt[:40]}...'")

        # Make 2 sequential calls
        for call_num in range(2):
            print(f"   Call {call_num + 1}/2 - Running OpenAI and Anthropic in parallel...")

            # Create parallel tasks for both LLMs
            tasks = [
                openai_client.query_with_file(openai_file_id, prompt, question),
                anthropic_client.query_with_file(anthropic_file_id, prompt, question)
            ]

            # Execute in parallel
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Check results
            for idx, (result, provider) in enumerate(zip(results, ["OpenAI", "Anthropic"])):
                if isinstance(result, Exception):
                    print(f"      {provider}: Error - {str(result)[:80]}...")
                else:
                    print(f"      {provider}: Success - {result[:60]}...")

            all_results.extend(results)

    print(f"\n3. Summary:")
    print(f"   Total calls made: {len(all_results)}")
    successful = sum(1 for r in all_results if not isinstance(r, Exception))
    print(f"   Successful: {successful}/{len(all_results)}")
    print("\n✅ Sequential execution test complete!")

if __name__ == "__main__":
    asyncio.run(test_sequential())
