#!/usr/bin/env python3
"""
Test Font 2 in isolation to see if it works correctly.
"""

import os
import sys
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont as RLTTFont
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_font2_isolation():
    """Test Font 2 in isolation."""
    
    # Find the most recent run
    runs_dir = "output/runs"
    if not os.path.exists(runs_dir):
        logger.error("No runs directory found")
        return
    
    # Get the most recent run
    runs = [d for d in os.listdir(runs_dir) if d.startswith("run_")]
    if not runs:
        logger.error("No runs found")
        return
    
    latest_run = sorted(runs)[-1]
    logger.info(f"Testing Font 2 isolation from run: {latest_run}")
    
    # Font paths
    font2_path = f"output/runs/{latest_run}/fonts/font2_{latest_run.split('_', 1)[1]}.ttf"
    
    if not os.path.exists(font2_path):
        logger.error("Font 2 file not found")
        return
    
    # Create test PDF
    test_pdf_path = "font2_isolation_test.pdf"
    c = canvas.Canvas(test_pdf_path, pagesize=(400, 300))
    
    try:
        # Register Font 2
        pdfmetrics.registerFont(RLTTFont("MaliciousFont2", font2_path))
        logger.info("✅ Font 2 registered successfully")
        
        y_position = 250
        
        # Test 1: Draw 's' with normal font (should show 's')
        c.setFont("Helvetica", 24)
        c.drawString(50, y_position, "s")
        c.setFont("Helvetica", 12)
        c.drawString(50, y_position - 30, "Helvetica: 's' (should show 's')")
        
        # Test 2: Draw 's' with Font 2 (should show 'a')
        y_position -= 80
        c.setFont("MaliciousFont2", 24)
        c.drawString(50, y_position, "s")
        c.setFont("Helvetica", 12)
        c.drawString(50, y_position - 30, "Font 2: 's' (should show 'a')")
        
        # Test 3: Draw 'a' with Font 2 (should show 'a')
        y_position -= 80
        c.setFont("MaliciousFont2", 24)
        c.drawString(50, y_position, "a")
        c.setFont("Helvetica", 12)
        c.drawString(50, y_position - 30, "Font 2: 'a' (should show 'a')")
        
        # Test 4: Draw 's' with Font 2 again
        y_position -= 80
        c.setFont("MaliciousFont2", 24)
        c.drawString(50, y_position, "s")
        c.setFont("Helvetica", 12)
        c.drawString(50, y_position - 30, "Font 2: 's' again (should show 'a')")
        
        # Add explanation
        y_position -= 80
        c.setFont("Helvetica", 10)
        c.drawString(50, y_position, "Font 2 Isolation Test")
        c.drawString(50, y_position - 15, "Expected: 's' should show 'a' when using Font 2")
        c.drawString(50, y_position - 30, "If Font 2 works: 's' → 'a'")
        c.drawString(50, y_position - 45, "If Font 2 doesn't work: 's' → 's'")
        
        c.save()
        logger.info(f"✅ Font 2 isolation test PDF created: {test_pdf_path}")
        logger.info("📄 Open the PDF to see if Font 2 works in isolation")
        
    except Exception as e:
        logger.error(f"❌ Font 2 isolation test failed: {e}")

if __name__ == "__main__":
    test_font2_isolation() 