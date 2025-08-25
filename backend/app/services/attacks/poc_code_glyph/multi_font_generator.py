#!/usr/bin/env python3
"""
Multi-Font Generator for Malicious Font Pipeline
Handles creation of multiple malicious fonts based on font strategies.
"""

import os
import sys
import datetime
import logging
from typing import List, Dict, Optional
from fontTools.ttLib import TTFont
from character_mapper import FontStrategy, MappingAnalysis

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MultiFontGenerator:
    """
    Generates multiple malicious fonts based on font strategies.
    """
    
    def __init__(self, base_font_path: str = "DejaVuSans.ttf"):
        """
        Initialize the multi-font generator.
        
        Args:
            base_font_path (str): Path to the base font file
        """
        self.base_font_path = base_font_path
        if not os.path.exists(base_font_path):
            raise FileNotFoundError(f"Base font not found: {base_font_path}")
        
        logger.info(f"Initialized MultiFontGenerator with base font: {base_font_path}")
    
    def create_fonts(self, font_strategies: List[FontStrategy], run_id: str) -> List[str]:
        """
        Create multiple malicious fonts based on font strategies.
        
        Args:
            font_strategies (List[FontStrategy]): List of font strategies
            run_id (str): Unique run identifier
            
        Returns:
            List[str]: List of created font file paths
        """
        logger.info(f"Creating {len(font_strategies)} malicious font(s) for run {run_id}")
        
        created_fonts = []
        
        for strategy in font_strategies:
            font_path = self._create_single_font(strategy, run_id)
            if font_path:
                created_fonts.append(font_path)
                logger.info(f"✓ Created font {strategy.font_id}: {font_path}")
        
        logger.info(f"✓ Successfully created {len(created_fonts)} font(s)")
        return created_fonts
    
    def _create_single_font(self, strategy: FontStrategy, run_id: str) -> Optional[str]:
        """
        Create a single malicious font based on a font strategy.
        
        Args:
            strategy (FontStrategy): The font strategy
            run_id (str): Unique run identifier
            
        Returns:
            Optional[str]: Path to created font file, or None if failed
        """
        try:
            # Create output directory
            fonts_dir = f"output/runs/{run_id}/fonts"
            os.makedirs(fonts_dir, exist_ok=True)
            
            # Generate font filename
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            font_filename = f"font{strategy.font_id}_{timestamp}.ttf"
            font_path = os.path.join(fonts_dir, font_filename)
            
            # Load base font - handle font collections
            font = None
            for font_number in range(6):  # Try font numbers 0-5
                try:
                    font = TTFont(self.base_font_path, fontNumber=font_number)
                    logger.debug(f"Successfully loaded font with fontNumber={font_number}")
                    break
                except Exception as e:
                    if font_number == 5:  # Last attempt
                        raise e
                    continue
            
            if font is None:
                raise Exception("Failed to load base font")
            
            # Apply character mappings
            self._apply_character_mappings(font, strategy.character_mappings)
            
            # Save malicious font
            font.save(font_path)
            font.close()
            
            logger.info(f"Applied {len(strategy.character_mappings)} mapping(s) to font {strategy.font_id}")
            return font_path
            
        except Exception as e:
            logger.error(f"Failed to create font {strategy.font_id}: {e}")
            return None
    
    def _apply_character_mappings(self, font: TTFont, character_mappings: Dict[str, str]) -> None:
        """
        Apply character mappings to a font.
        
        Args:
            font (TTFont): The font to modify
            character_mappings (Dict[str, str]): Character mappings to apply
        """
        # Get the cmap table
        cmap = font.getBestCmap()
        
        # Find the cmap subtable to modify
        for table in font['cmap'].tables:
            if table.format in [4, 12]:  # Format 4 (Unicode) or Format 12 (Unicode)
                for input_char, output_char in character_mappings.items():
                    input_code = ord(input_char)
                    output_code = ord(output_char)
                    
                    # Map input character to output character's glyph
                    if input_code in table.cmap and output_code in table.cmap:
                        table.cmap[input_code] = table.cmap[output_code]
                        logger.info(f"Mapped '{input_char}' (U+{input_code:04X}) → '{output_char}' (U+{output_code:04X})")
                break
    
    def create_font_configs(self, analysis: MappingAnalysis, run_id: str) -> List[Dict]:
        """
        Create font configurations for the mapping analysis.
        
        Args:
            analysis (MappingAnalysis): The mapping analysis
            run_id (str): Unique run identifier
            
        Returns:
            List[Dict]: List of font configurations
        """
        logger.info(f"Creating font configurations for {analysis.required_fonts} font(s)")
        
        # Create fonts
        font_paths = self.create_fonts(analysis.font_strategies, run_id)
        
        # Create font configurations
        font_configs = []
        for i, (strategy, font_path) in enumerate(zip(analysis.font_strategies, font_paths)):
            config = {
                "font_id": strategy.font_id,
                "font_path": font_path,
                "font_name": f"MaliciousFont{strategy.font_id}",
                "character_mappings": strategy.character_mappings,
                "apply_positions": strategy.apply_positions,
                "priority": strategy.priority,
                "description": strategy.description
            }
            font_configs.append(config)
        
        logger.info(f"✓ Created {len(font_configs)} font configuration(s)")
        return font_configs
    
    def verify_font_mappings(self, font_path: str, character_mappings: Dict[str, str]) -> bool:
        """
        Verify that a font has the correct character mappings.
        
        Args:
            font_path (str): Path to the font file
            character_mappings (Dict[str, str]): Expected character mappings
            
        Returns:
            bool: True if mappings are correct, False otherwise
        """
        try:
            font = TTFont(font_path)
            cmap = font.getBestCmap()
            
            for input_char, output_char in character_mappings.items():
                input_code = ord(input_char)
                output_code = ord(output_char)
                
                if input_code not in cmap:
                    logger.warning(f"Input character '{input_char}' not found in font")
                    return False
                
                # Check if the mapping is correct
                if cmap[input_code] != cmap[output_code]:
                    logger.warning(f"Mapping verification failed for '{input_char}' → '{output_char}'")
                    return False
            
            font.close()
            logger.info(f"✓ Font mapping verification successful for {len(character_mappings)} mapping(s)")
            return True
            
        except Exception as e:
            logger.error(f"Font verification failed: {e}")
            return False
    
    def get_font_summary(self, font_configs: List[Dict]) -> Dict:
        """
        Get a summary of created fonts.
        
        Args:
            font_configs (List[Dict]): List of font configurations
            
        Returns:
            Dict: Summary information
        """
        summary = {
            "total_fonts": len(font_configs),
            "fonts": []
        }
        
        for config in font_configs:
            font_info = {
                "font_id": config["font_id"],
                "font_name": config["font_name"],
                "font_path": config["font_path"],
                "mappings": len(config["character_mappings"]),
                "positions": len(config["apply_positions"]),
                "priority": config["priority"],
                "description": config["description"]
            }
            summary["fonts"].append(font_info)
        
        return summary

def create_malicious_fonts(analysis: MappingAnalysis, run_id: str) -> List[Dict]:
    """
    Create malicious fonts based on mapping analysis.
    
    Args:
        analysis (MappingAnalysis): The mapping analysis
        run_id (str): Unique run identifier
        
    Returns:
        List[Dict]: List of font configurations
    """
    generator = MultiFontGenerator()
    return generator.create_font_configs(analysis, run_id)

if __name__ == "__main__":
    # Test the multi-font generator
    from character_mapper import analyze_entity_mapping
    
    test_cases = [
        ("Russia", "Canada"),
        ("Hello", "World"),
    ]
    
    for input_entity, output_entity in test_cases:
        print(f"\nTesting: '{input_entity}' → '{output_entity}'")
        try:
            analysis = analyze_entity_mapping(input_entity, output_entity)
            run_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            font_configs = create_malicious_fonts(analysis, run_id)
            
            generator = MultiFontGenerator()
            summary = generator.get_font_summary(font_configs)
            print(f"Created {summary['total_fonts']} font(s)")
            
            for font in summary["fonts"]:
                print(f"  Font {font['font_id']}: {font['mappings']} mapping(s)")
                
        except Exception as e:
            print(f"Error: {e}") 