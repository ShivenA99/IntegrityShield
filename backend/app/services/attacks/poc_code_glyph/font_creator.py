#!/usr/bin/env python3
"""
Advanced Font Creator for Malicious Font Injection Attack
Based on the research paper: "Invisible Prompts, Visible Threats: Malicious Font Injection in External Resources for Large Language Models"

This script creates a font with manipulated cmap tables to achieve visual-semantic mismatch.
"""

import os
import sys
import datetime
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import _c_m_a_p
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MaliciousFontCreator:
    """
    Creates fonts with manipulated cmap tables for visual-semantic deception attacks.
    """
    
    def __init__(self, source_font_path, font_number=0):
        """
        Initialize with a source font file.
        
        Args:
            source_font_path (str): Path to the source TTF font file
            font_number (int): The font number to load from a font collection (default: 0)
        """
        if not os.path.exists(source_font_path):
            raise FileNotFoundError(f"Source font not found: {source_font_path}")
        
        self.source_font_path = source_font_path
        self.font_number = font_number
        self.font = TTFont(source_font_path, fontNumber=font_number)
        self.cmap = self.font.getBestCmap()
        self.word_mappings = {}
        
        logger.info(f"Loaded source font: {source_font_path} (font number: {font_number})")
        logger.info(f"Font contains {len(self.cmap)} character mappings")
    
    def add_word_mapping(self, target_word, visual_word):
        """
        Add a word mapping for visual-semantic deception.
        
        Args:
            target_word (str): The word that will be processed by AI systems
            visual_word (str): The word that will be displayed visually
        """
        if len(target_word) != len(visual_word):
            raise ValueError(f"Words must have same length: {target_word} vs {visual_word}")
        
        self.word_mappings[target_word] = visual_word
        logger.info(f"Added mapping: '{target_word}' -> '{visual_word}'")
    
    def create_malicious_font(self, output_path):
        """
        Create a malicious font with manipulated cmap tables.
        
        Args:
            output_path (str): Path to save the malicious font
        """
        logger.info("Creating malicious font...")
        
        # Create a copy of the font
        malicious_font = TTFont(self.source_font_path, fontNumber=self.font_number)
        
        # Get the cmap table
        cmap_table = malicious_font.get('cmap')
        if not cmap_table:
            raise ValueError("Font does not contain cmap table")
        
        # Find the best cmap subtable (usually format 4 or 12)
        best_subtable = None
        for table in cmap_table.tables:
            if table.format in [4, 12]:  # Format 4 (Unicode) or Format 12 (Unicode)
                best_subtable = table
                break
        
        if not best_subtable:
            logger.warning("No suitable cmap subtable found, using first available")
            best_subtable = cmap_table.tables[0]
        
        logger.info(f"Using cmap subtable: format {best_subtable.format}")
        
        # Create character mappings
        char_mappings = {}
        for target_word, visual_word in self.word_mappings.items():
            for i, (target_char, visual_char) in enumerate(zip(target_word, visual_word)):
                target_code = ord(target_char)
                visual_code = ord(visual_char)
                
                # Map target character to visual character's glyph
                char_mappings[target_code] = visual_code
                logger.info(f"Mapping: {target_char} (U+{target_code:04X}) -> {visual_char} (U+{visual_code:04X})")
        
        # Apply mappings to the cmap subtable
        if hasattr(best_subtable, 'cmap'):
            for target_code, visual_code in char_mappings.items():
                # Get the glyph ID for the visual character
                visual_glyph_id = best_subtable.cmap.get(visual_code)
                if visual_glyph_id is not None:
                    # Map target character to the visual character's glyph
                    best_subtable.cmap[target_code] = visual_glyph_id
                    logger.info(f"Applied mapping: U+{target_code:04X} -> glyph {visual_glyph_id}")
                else:
                    logger.warning(f"Visual character U+{visual_code:04X} not found in font")
        
        # Save the malicious font
        malicious_font.save(output_path)
        logger.info(f"✓ Malicious font saved to: {output_path}")
        
        return output_path
    
    def verify_mappings(self, font_path):
        """
        Verify that the character mappings are working correctly.
        
        Args:
            font_path (str): Path to the font to verify
        """
        logger.info("Verifying character mappings...")
        
        try:
            test_font = TTFont(font_path)
            cmap = test_font.getBestCmap()
            
            for target_word, visual_word in self.word_mappings.items():
                logger.info(f"Testing mapping: '{target_word}' -> '{visual_word}'")
                
                for target_char, visual_char in zip(target_word, visual_word):
                    target_code = ord(target_char)
                    visual_code = ord(visual_char)
                    
                    if target_code in cmap:
                        mapped_glyph = cmap[target_code]
                        if visual_code in cmap:
                            expected_glyph = cmap[visual_code]
                            if mapped_glyph == expected_glyph:
                                logger.info(f"✓ {target_char} -> {visual_char} (glyph {mapped_glyph})")
                            else:
                                logger.warning(f"✗ {target_char} -> {visual_char} (glyph mismatch: {mapped_glyph} vs {expected_glyph})")
                        else:
                            logger.warning(f"✗ Visual character {visual_char} not found in font")
                    else:
                        logger.warning(f"✗ Target character {target_char} not found in font")
        
        except Exception as e:
            logger.error(f"Error verifying font: {e}")
    
    def close(self):
        """Close the font and free resources."""
        if hasattr(self, 'font'):
            self.font.close()

def create_demo_font():
    """
    Create a demo malicious font with Russia->Canada mapping.
    """
    try:
        # Check if source font exists
        source_font_path = "DejaVuSans.ttf"
        if not os.path.exists(source_font_path):
            logger.error(f"Source font not found: {source_font_path}")
            logger.info("Please download DejaVuSans.ttf or use another TTF font")
            return None
        
        # Create font creator - try different font numbers for font collections
        font_path = None
        for font_number in range(6):  # Try font numbers 0-5
            try:
                creator = MaliciousFontCreator(source_font_path, font_number=font_number)
                logger.info(f"Successfully loaded font with font number {font_number}")
                font_path = source_font_path
                break
            except Exception as e:
                logger.warning(f"Failed to load font with font number {font_number}: {e}")
                continue
        
        if font_path is None:
            logger.error("Could not load font with any font number")
            return None
        
        # Add word mapping for the attack - only AWS->DNS
        creator.add_word_mapping("AWS", "DNS")
        
        # Create timestamp for unique filename
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"output/fonts/malicious_font_{timestamp}.ttf"
        
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Create the malicious font
        malicious_font_path = creator.create_malicious_font(output_path)
        
        # Verify the mappings
        creator.verify_mappings(malicious_font_path)
        
        creator.close()
        return malicious_font_path
        
    except Exception as e:
        logger.error(f"Error creating demo font: {e}")
        return None

if __name__ == "__main__":
    malicious_font = create_demo_font()
    if malicious_font:
        logger.info(f"✓ Demo malicious font created: {malicious_font}")
    else:
        logger.error("✗ Failed to create malicious font") 