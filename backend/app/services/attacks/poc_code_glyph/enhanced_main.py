#!/usr/bin/env python3
"""
Enhanced Main Pipeline for Malicious Font Attack
Orchestrates the complete pipeline with input validation, character mapping,
multi-font generation, and enhanced PDF creation.
"""

import os
import sys
import datetime
import logging
from typing import Dict, List, Optional

# Import our modules
from input_validator import validate_pipeline_inputs
from character_mapper import analyze_entity_mapping
from multi_font_generator import create_malicious_fonts
from enhanced_pdf_generator import create_malicious_pdf
from run_manager import create_run_manager
# Add prebuilt entry
from enhanced_pdf_generator import create_malicious_pdf_prebuilt

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('malicious_font_pipeline.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class EnhancedMaliciousFontPipeline:
    """
    Enhanced pipeline for creating malicious font attacks.
    """
    
    def __init__(self, font_mode: str = "dynamic", prebuilt_dir: str = "demo/prebuilt_fonts/DejaVuSans/v1"):
        self.run_manager = create_run_manager()
        self.font_mode = font_mode
        self.prebuilt_dir = prebuilt_dir
        logger.info("✓ Enhanced Malicious Font Pipeline initialized")
    
    def run_pipeline(self, input_string: str, input_entity: str, output_entity: str) -> Dict:
        """
        Run the complete malicious font pipeline.
        """
        logger.info("=" * 80)
        logger.info("🚀 STARTING ENHANCED MALICIOUS FONT PIPELINE")
        logger.info("=" * 80)
        
        # Step 1: Input Validation
        logger.info("📋 STEP 1: INPUT VALIDATION")
        is_valid, compatibility = validate_pipeline_inputs(input_string, input_entity, output_entity)
        if not is_valid:
            raise ValueError("Input validation failed")
        logger.info("✓ Input validation passed")
        
        # Step 2: Character Mapping Analysis (kept for reporting)
        logger.info("🔍 STEP 2: CHARACTER MAPPING ANALYSIS")
        mapping_analysis = analyze_entity_mapping(input_entity, output_entity)
        logger.info(f"✓ Mapping analysis completed: {mapping_analysis.required_fonts} font(s) required (dynamic mode)")
        
        # Step 3: Create Run Environment
        logger.info("📁 STEP 3: CREATING RUN ENVIRONMENT")
        run_id = self.run_manager.create_run_id()
        run_dir = self.run_manager.create_run_directory(run_id)
        logger.info(f"✓ Run environment created: {run_id}")
        
        # Step 4 & 5 depend on mode
        if self.font_mode == "prebuilt":
            logger.info("🎨 STEP 4: USING PREBUILT PAIR-FONTS (no dynamic generation)")
            logger.info("📄 STEP 5: CREATING MALICIOUS PDF (prebuilt mode)")
            pdf_result = create_malicious_pdf_prebuilt(
                input_string, input_entity, output_entity, self.prebuilt_dir, run_id
            )
            logger.info(f"✓ PDF created: {pdf_result['pdf_path']}")
        else:
            # Dynamic mode (existing path)
            logger.info("🎨 STEP 4: GENERATING MALICIOUS FONTS")
            font_configs = create_malicious_fonts(mapping_analysis, run_id)
            logger.info(f"✓ Generated {len(font_configs)} malicious font(s)")
            
            logger.info("📄 STEP 5: CREATING MALICIOUS PDF")
            pdf_result = create_malicious_pdf(input_string, input_entity, output_entity, font_configs, run_id)
            logger.info(f"✓ PDF created: {pdf_result['pdf_path']}")
        
        # Step 6: Generate Results Summary
        logger.info("📊 STEP 6: GENERATING RESULTS SUMMARY")
        results = self._generate_results_summary(
            input_string, input_entity, output_entity,
            mapping_analysis, [] if self.font_mode == "prebuilt" else font_configs, pdf_result, run_id
        )
        
        logger.info("=" * 80)
        logger.info("✅ PIPELINE COMPLETED SUCCESSFULLY")
        logger.info("=" * 80)
        
        return results
    
    def _generate_results_summary(self, input_string: str, input_entity: str, output_entity: str,
                                mapping_analysis, font_configs: List[Dict], pdf_result: Dict, run_id: str) -> Dict:
        """Generate a comprehensive results summary."""
        summary = {
            "run_id": run_id,
            "timestamp": datetime.datetime.now().isoformat(),
            "pipeline_version": "2.0",
            
            # Input information
            "input": {
                "input_string": input_string,
                "input_entity": input_entity,
                "output_entity": output_entity
            },
            
            # Analysis information
            "analysis": {
                "strategy_type": mapping_analysis.strategy_type,
                "required_fonts": mapping_analysis.required_fonts,
                "character_mappings": mapping_analysis.character_mappings,
                "duplicates": len(mapping_analysis.duplicate_positions)
            },
            
            # Font information
            "fonts": {
                "total_fonts": len(font_configs),
                "font_configs": font_configs
            },
            
            # Output information
            "output": {
                "pdf_path": pdf_result["pdf_path"],
                "metadata_path": pdf_result["metadata_path"],
                "visual_result": input_string.replace(input_entity, output_entity),
                "actual_result": input_string
            },
            
            # File paths
            "files": {
                "pdf": pdf_result["pdf_path"],
                "metadata": pdf_result["metadata_path"],
                "fonts": [config["font_path"] for config in font_configs] if font_configs else []
            }
        }
        return summary
    
    def print_results(self, results: Dict) -> None:
        """Print a formatted summary of the pipeline results."""
        print("\n" + "=" * 80)
        print("🎯 MALICIOUS FONT ATTACK RESULTS")
        print("=" * 80)
        
        print(f"📋 Run ID: {results['run_id']}")
        print(f"⏰ Timestamp: {results['timestamp']}")
        print()
        
        print("📝 INPUT INFORMATION:")
        print(f"  • Input String: '{results['input']['input_string']}'")
        print(f"  • Input Entity: '{results['input']['input_entity']}'")
        print(f"  • Output Entity: '{results['input']['output_entity']}'")
        print()
        
        print("🔍 ANALYSIS RESULTS:")
        print(f"  • Strategy Type: {results['analysis']['strategy_type']}")
        print(f"  • Required Fonts: {results['analysis']['required_fonts']}")
        print(f"  • Character Mappings: {len(results['analysis']['character_mappings'])}")
        print(f"  • Duplicate Characters: {results['analysis']['duplicates']}")
        print()
        
        print("🎨 FONT INFORMATION:")
        print(f"  • Total Fonts Created: {results['fonts']['total_fonts']}")
        for i, config in enumerate(results['fonts']['font_configs'], 1):
            print(f"  • Font {i}: {config['font_name']} ({len(config['character_mappings'])} mappings)")
        print()
        
        print("📄 OUTPUT INFORMATION:")
        print(f"  • PDF File: {results['output']['pdf_path']}")
        print(f"  • Metadata File: {results['output']['metadata_path']}")
        print(f"  • Visual Result: '{results['output']['visual_result']}'")
        print(f"  • Actual Result: '{results['output']['actual_result']}'")
        print()
        
        print("📁 GENERATED FILES:")
        print(f"  • PDF: {results['files']['pdf']}")
        print(f"  • Metadata: {results['files']['metadata']}")
        for i, font_path in enumerate(results['files']['fonts'], 1):
            print(f"  • Font {i}: {font_path}")
        
        print("\n" + "=" * 80)
        print("✅ Pipeline completed successfully!")
        print("=" * 80)

def run_enhanced_pipeline(input_string: str, input_entity: str, output_entity: str, *, font_mode: str = "dynamic", prebuilt_dir: str = "demo/prebuilt_fonts/DejaVuSans/v1") -> Dict:
    pipeline = EnhancedMaliciousFontPipeline(font_mode=font_mode, prebuilt_dir=prebuilt_dir)
    results = pipeline.run_pipeline(input_string, input_entity, output_entity)
    pipeline.print_results(results)
    return results


def main():
    """Main function for command-line usage."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Enhanced Malicious Font Pipeline")
    parser.add_argument("--input-string", required=True, help="Complete input text")
    parser.add_argument("--input-entity", required=True, help="Entity to attack")
    parser.add_argument("--output-entity", required=True, help="Desired visual output")
    # New flags for prebuilt mode
    parser.add_argument("--font-mode", choices=["dynamic", "prebuilt"], default="dynamic", help="Font generation mode")
    parser.add_argument("--prebuilt-dir", default="demo/prebuilt_fonts/DejaVuSans/v1", help="Directory containing prebuilt pair-fonts and base font")
    
    args = parser.parse_args()
    
    try:
        results = run_enhanced_pipeline(args.input_string, args.input_entity, args.output_entity, font_mode=args.font_mode, prebuilt_dir=args.prebuilt_dir)
        print(f"\n🎉 Pipeline completed! Check the generated files in: output/runs/{results['run_id']}/")
        
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        print(f"\n❌ Pipeline failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    # Example usage
    if len(sys.argv) == 1:
        # Run with example inputs
        print("Running with example inputs...")
        example_input = "What is the capital of Russia?"
        example_input_entity = "Russia"
        example_output_entity = "Canada"
        
        try:
            results = run_enhanced_pipeline(example_input, example_input_entity, example_output_entity, font_mode="prebuilt")
            print(f"\n🎉 Example pipeline completed! Check the generated files in: output/runs/{results['run_id']}/")
        except Exception as e:
            logger.error(f"Example pipeline failed: {e}")
            print(f"\n❌ Example pipeline failed: {e}")
    else:
        main() 