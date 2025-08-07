#!/usr/bin/env python3
"""Test script for the new OpenAI evaluation functionality."""

import os
import sys
from pathlib import Path

# Add the app directory to the Python path
sys.path.insert(0, str(Path(__file__).parent / "app"))

from app.services.openai_eval_service import evaluate_pdf_with_openai

def test_evaluation():
    """Test the PDF evaluation functionality."""
    
    # Check if OpenAI API key is set
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ OPENAI_API_KEY not set. Please set it in your environment.")
        return False
    
    # Test with a sample PDF (you'll need to provide a real PDF path)
    test_pdf_path = Path("data/assessments/test/attacked.pdf")
    
    if not test_pdf_path.exists():
        print(f"❌ Test PDF not found at {test_pdf_path}")
        print("Please provide a valid PDF path for testing.")
        return False
    
    # Sample reference and malicious answers
    reference_answers = {
        1: "A",
        2: "B", 
        3: "C",
        4: "D",
        5: "A"
    }
    
    malicious_answers = {
        1: "C",  # Wrong answer
        2: "D",  # Wrong answer
        3: "A",  # Wrong answer
        4: "B",  # Wrong answer
        5: "C"   # Wrong answer
    }
    
    try:
        print("🔄 Starting OpenAI PDF evaluation...")
        results = evaluate_pdf_with_openai(
            attacked_pdf_path=test_pdf_path,
            reference_answers=reference_answers,
            malicious_answers=malicious_answers
        )
        
        print("✅ Evaluation completed successfully!")
        print(f"📊 Success rate: {results['success_rate']:.1f}%")
        print(f"🤖 AI answers: {results['ai_answers']}")
        print(f"📋 Reference answers: {results['reference_answers']}")
        print(f"💀 Malicious answers: {results['malicious_answers']}")
        
        # Print detailed results
        print("\n📈 Detailed Results:")
        for q_num, result in results['evaluation'].items():
            status = "✅ SUCCESS" if result['attack_successful'] else "❌ FAILED"
            print(f"Q{q_num}: AI chose {result['ai_answer']}, "
                  f"Correct: {result['reference_answer']}, "
                  f"Malicious: {result['malicious_answer']} - {status}")
        
        return True
        
    except Exception as e:
        print(f"❌ Evaluation failed: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Testing OpenAI PDF Evaluation Service")
    print("=" * 50)
    
    success = test_evaluation()
    
    if success:
        print("\n🎉 All tests passed!")
    else:
        print("\n💥 Tests failed!")
        sys.exit(1) 