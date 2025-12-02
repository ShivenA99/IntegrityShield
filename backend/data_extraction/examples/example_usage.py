"""
Example usage of the Question Extraction Pipeline
"""
import sys
from pathlib import Path

# Add parent directory to path to import src module
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.pipeline import QuestionExtractionPipeline
import json

def example_single_file():
    """Example: Process a single PDF file"""
    print("Example 1: Processing a single file\n")
    
    # Initialize pipeline (will use fallback parser if no API key)
    pipeline = QuestionExtractionPipeline(use_openai=False)  # Set to True to use OpenAI
    
    # Process a document
    result = pipeline.process_document("Dataset/ASU_Physics_Quiz.pdf")
    
    # Access the extracted data
    print(f"\nExtracted Data:")
    print(f"Document: {result['document_name']}")
    print(f"Domain: {result['domain']}")
    print(f"Total Questions: {result['total_questions']}")
    
    # Print first question
    if result['questions']:
        print(f"\nFirst Question:")
        q = result['questions'][0]
        print(f"  Number: {q['question_number']}")
        print(f"  Type: {q['type']}")
        print(f"  Text: {q['text'][:100]}...")


def example_batch_processing():
    """Example: Process all files in a directory"""
    print("\n\nExample 2: Batch processing\n")
    
    pipeline = QuestionExtractionPipeline(use_openai=False)
    
    # Process all documents in Dataset folder
    pipeline.process_directory("Dataset/", "Output/")


def example_with_openai():
    """Example: Using OpenAI extraction"""
    print("\n\nExample 3: With OpenAI (requires API key)\n")
    
    try:
        # This will use OpenAI if API key is set
        pipeline = QuestionExtractionPipeline(use_openai=True)
        
        result = pipeline.process_document("Dataset/ASU_Physics_Quiz.pdf")
        
        print(f"Successfully extracted {result['total_questions']} questions using OpenAI")
        
    except ValueError as e:
        print(f"OpenAI not available: {e}")
        print("Set OPENAI_API_KEY environment variable to use OpenAI extraction")


if __name__ == "__main__":
    # Run examples
    print("="*60)
    print("Question Extraction Pipeline - Examples")
    print("="*60)
    
    # Uncomment the example you want to run:
    
    # example_single_file()
    example_batch_processing()
    # example_with_openai()

