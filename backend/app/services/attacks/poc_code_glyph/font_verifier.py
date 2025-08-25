#!/usr/bin/env python3
"""
Font Verification Tool for Malicious Font Injection Attack
Verifies that the malicious font mappings are working correctly.
"""

import os
import sys
from fontTools.ttLib import TTFont
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class FontVerifier:
    """
    Verifies malicious font mappings and provides detailed analysis.
    """
    
    def __init__(self, font_path):
        """
        Initialize with a font file.
        
        Args:
            font_path (str): Path to the font file
        """
        if not os.path.exists(font_path):
            raise FileNotFoundError(f"Font file not found: {font_path}")
        
        self.font_path = font_path
        self.font = TTFont(font_path)
        self.cmap = self.font.getBestCmap()
        
        logger.info(f"Loaded font for verification: {font_path}")
        logger.info(f"Font contains {len(self.cmap)} character mappings")
    
    def analyze_cmap_tables(self):
        """
        Analyze the cmap tables in the font.
        """
        logger.info("Analyzing cmap tables...")
        
        cmap_table = self.font.get('cmap')
        if not cmap_table:
            logger.error("Font does not contain cmap table")
            return
        
        logger.info(f"Found {len(cmap_table.tables)} cmap subtables")
        
        for i, table in enumerate(cmap_table.tables):
            logger.info(f"Subtable {i}:")
            logger.info(f"  Format: {table.format}")
            logger.info(f"  Platform ID: {table.platformID}")
            logger.info(f"  Platform Encoding ID: {table.platEncID}")
            try:
                logger.info(f"  Language ID: {table.languageID}")
            except AttributeError:
                logger.info(f"  Language ID: Not available")
            logger.info(f"  Number of mappings: {len(table.cmap)}")
    
    def test_character_mappings(self, test_mappings):
        """
        Test specific character mappings.
        
        Args:
            test_mappings (dict): Dictionary of {target_char: expected_visual_char}
        """
        logger.info("Testing character mappings...")
        
        for target_char, expected_visual_char in test_mappings.items():
            target_code = ord(target_char)
            expected_code = ord(expected_visual_char)
            
            if target_code in self.cmap:
                mapped_glyph = self.cmap[target_code]
                if expected_code in self.cmap:
                    expected_glyph = self.cmap[expected_code]
                    if mapped_glyph == expected_glyph:
                        logger.info(f"✓ {target_char} -> {expected_visual_char} (glyph {mapped_glyph})")
                    else:
                        logger.warning(f"✗ {target_char} -> {expected_visual_char} (glyph mismatch: {mapped_glyph} vs {expected_glyph})")
                else:
                    logger.warning(f"✗ Expected visual character '{expected_visual_char}' not found in font")
            else:
                logger.warning(f"✗ Target character '{target_char}' not found in font")
    
    def test_word_mappings(self, test_words):
        """
        Test word-level mappings.
        
        Args:
            test_words (dict): Dictionary of {target_word: expected_visual_word}
        """
        logger.info("Testing word mappings...")
        
        for target_word, expected_visual_word in test_words.items():
            logger.info(f"Testing: '{target_word}' -> '{expected_visual_word}'")
            
            if len(target_word) != len(expected_visual_word):
                logger.error(f"Word length mismatch: {len(target_word)} vs {len(expected_visual_word)}")
                continue
            
            all_mapped = True
            for target_char, expected_char in zip(target_word, expected_visual_word):
                target_code = ord(target_char)
                expected_code = ord(expected_char)
                
                if target_code in self.cmap and expected_code in self.cmap:
                    if self.cmap[target_code] != self.cmap[expected_code]:
                        logger.warning(f"  ✗ {target_char} -> {expected_char} (glyph mismatch)")
                        all_mapped = False
                    else:
                        logger.info(f"  ✓ {target_char} -> {expected_char}")
                else:
                    logger.warning(f"  ✗ Character not found in font")
                    all_mapped = False
            
            if all_mapped:
                logger.info(f"✓ Word mapping successful: '{target_word}' -> '{expected_visual_word}'")
            else:
                logger.warning(f"✗ Word mapping failed: '{target_word}' -> '{expected_visual_word}'")
    
    def generate_test_text(self):
        """
        Generate test text to verify the malicious font.
        """
        logger.info("Generating test text...")
        
        # Test the AWS->DNS mapping
        test_text = "What is the full form of AWS?"
        logger.info(f"Test text: '{test_text}'")
        logger.info("This should appear as: 'What is the full form of DNS?'")
        
        return test_text
    
    def close(self):
        """Close the font and free resources."""
        if hasattr(self, 'font'):
            self.font.close()

def verify_malicious_font():
    """
    Verify the malicious font mappings.
    """
    try:
        # Find the most recent malicious font
        fonts_dir = "output/fonts"
        if not os.path.exists(fonts_dir):
            logger.error(f"Fonts directory not found: {fonts_dir}")
            logger.info("Please run font_creator.py first to create a malicious font")
            return False
        
        # Find the most recent malicious font file
        font_files = [f for f in os.listdir(fonts_dir) if f.startswith("malicious_font_") and f.endswith(".ttf")]
        if not font_files:
            logger.error("No malicious font files found")
            logger.info("Please run font_creator.py first to create a malicious font")
            return False
        
        # Sort by timestamp and get the most recent
        font_files.sort(reverse=True)
        latest_font = os.path.join(fonts_dir, font_files[0])
        logger.info(f"Using malicious font: {latest_font}")
        
        verifier = FontVerifier(latest_font)
        
        # Analyze cmap tables
        verifier.analyze_cmap_tables()
        
        # Test character mappings for AWS->DNS
        char_mappings = {
            'A': 'D', 'W': 'N', 'S': 'S'
        }
        verifier.test_character_mappings(char_mappings)
        
        # Test word mappings
        word_mappings = {
            "AWS": "DNS"
        }
        verifier.test_word_mappings(word_mappings)
        
        # Generate test text
        test_text = verifier.generate_test_text()
        
        verifier.close()
        
        logger.info("=" * 60)
        logger.info("FONT VERIFICATION COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Font: {latest_font}")
        logger.info(f"Test text: '{test_text}'")
        logger.info("Expected visual: 'What is the full form of DNS?'")
        logger.info("=" * 60)
        
        return True
        
    except Exception as e:
        logger.error(f"Error verifying font: {e}")
        return False

if __name__ == "__main__":
    success = verify_malicious_font()
    if success:
        logger.info("✓ Font verification completed successfully")
    else:
        logger.error("✗ Font verification failed") 