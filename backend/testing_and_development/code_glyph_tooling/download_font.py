#!/usr/bin/env python3
"""
Download DejaVu Sans font for the malicious font demonstration.
"""

import os
import urllib.request
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def download_dejavu_font():
    """
    Download DejaVu Sans font if it doesn't exist.
    """
    # Try multiple URLs for the font
    font_urls = [
        "https://github.com/dejavu-fonts/dejavu-fonts/raw/master/ttf/DejaVuSans.ttf",
        "https://raw.githubusercontent.com/dejavu-fonts/dejavu-fonts/master/ttf/DejaVuSans.ttf",
        "https://github.com/dejavu-fonts/dejavu-fonts/blob/master/ttf/DejaVuSans.ttf?raw=true"
    ]
    
    font_path = "DejaVuSans.ttf"
    
    if os.path.exists(font_path):
        logger.info(f"Font already exists: {font_path}")
        return True
    
    for i, font_url in enumerate(font_urls):
        logger.info(f"Attempting to download font from URL {i+1}: {font_url}")
        
        try:
            urllib.request.urlretrieve(font_url, font_path)
            logger.info(f"✓ Font downloaded successfully: {font_path}")
            return True
        except Exception as e:
            logger.warning(f"Failed to download from URL {i+1}: {e}")
            continue
    
    logger.error("✗ Failed to download font from all URLs")
    logger.info("Please download DejaVuSans.ttf manually from:")
    logger.info("https://dejavu-fonts.github.io/")
    logger.info("Or use any other TTF font file and rename it to DejaVuSans.ttf")
    return False

if __name__ == "__main__":
    download_dejavu_font() 