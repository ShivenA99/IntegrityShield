"""
Main entry point for the Question Extraction Pipeline
Enhanced with Mistral OCR integration
"""
import argparse
import sys
from pathlib import Path

from src.pipeline import QuestionExtractionPipeline
from config import DATASET_DIR, OUTPUT_DIR


def main():
    """Main CLI interface"""
    parser = argparse.ArgumentParser(
        description="Extract questions from PDF/DOCX/TXT documents using hybrid PyMuPDF + Mistral OCR + GPT-4 Vision pipeline"
    )
    
    parser.add_argument(
        "input",
        nargs="?",
        default=str(DATASET_DIR),
        help="Input file or directory path (default: Dataset/)"
    )
    
    parser.add_argument(
        "-o", "--output",
        help="Output directory for JSON files (default: Output/)"
    )
    
    parser.add_argument(
        "--no-openai",
        action="store_true",
        help="Skip OpenAI extraction and use only fallback parser"
    )
    
    parser.add_argument(
        "--no-mistral",
        action="store_true",
        help="Skip Mistral OCR and use only PyMuPDF for text extraction"
    )
    
    parser.add_argument(
        "--openai-key",
        help="OpenAI API key (overrides OPENAI_API_KEY env var)"
    )
    
    # Legacy support for --api-key
    parser.add_argument(
        "--api-key",
        help="(Deprecated) Use --openai-key instead"
    )
    
    # LaTeX reconstruction options
    parser.add_argument(
        "--enable-latex",
        action="store_true",
        help="Enable LaTeX reconstruction (generates .tex, .md, structured JSON)"
    )
    
    parser.add_argument(
        "--latex-images",
        action="store_true",
        default=True,
        help="Include images in LaTeX output (default: True)"
    )
    
    parser.add_argument(
        "--no-latex-images",
        action="store_false",
        dest="latex_images",
        help="Disable image extraction for LaTeX"
    )
    
    parser.add_argument(
        "--latex-compile",
        action="store_true",
        help="Compile LaTeX to PDF (requires pdflatex or xelatex)"
    )
    
    args = parser.parse_args()
    
    # Handle legacy --api-key
    openai_key = args.openai_key or args.api_key
    
    # Initialize pipeline
    # Note: Mistral API key is always loaded from .env file for security
    use_openai = not args.no_openai
    use_mistral = not args.no_mistral
    
    pipeline = QuestionExtractionPipeline(
        use_openai=use_openai,
        use_mistral=use_mistral,
        openai_api_key=openai_key,
        enable_latex=args.enable_latex,
        latex_include_images=args.latex_images,
        latex_compile_pdf=args.latex_compile
    )
    
    # Process input
    input_path = Path(args.input)
    
    if not input_path.exists():
        print(f"Error: Input path does not exist: {input_path}")
        sys.exit(1)
    
    try:
        if input_path.is_file():
            # Process single file
            output_path = None
            if args.output:
                output_dir = Path(args.output)
                output_dir.mkdir(parents=True, exist_ok=True)
                output_path = output_dir / f"{input_path.stem}_extracted.json"
            
            pipeline.process_document(str(input_path), str(output_path) if output_path else None)
            
        elif input_path.is_dir():
            # Process directory
            output_dir = args.output or str(OUTPUT_DIR)
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            
            pipeline.process_directory(str(input_path), output_dir)
        else:
            print(f"Error: Invalid input path: {input_path}")
            sys.exit(1)
    
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(0)
    
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

