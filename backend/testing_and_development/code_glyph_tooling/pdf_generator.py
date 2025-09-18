#!/usr/bin/env python3
"""
PDF Generator for Malicious Font Injection Attack
Creates PDFs with visual-semantic mismatch using manipulated fonts.
"""

import os
import sys
import datetime
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.units import inch
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MaliciousPDFGenerator:
    """
    Generates PDFs with malicious fonts for visual-semantic deception.
    """
    
    def __init__(self, malicious_font_path):
        """
        Initialize with a malicious font.
        
        Args:
            malicious_font_path (str): Path to the malicious font file
        """
        if not os.path.exists(malicious_font_path):
            raise FileNotFoundError(f"Malicious font not found: {malicious_font_path}")
        
        self.malicious_font_path = malicious_font_path
        self.font_name = "MaliciousFont"
        
        # Register the malicious font
        try:
            pdfmetrics.registerFont(TTFont(self.font_name, malicious_font_path))
            logger.info(f"Registered malicious font: {malicious_font_path}")
        except Exception as e:
            logger.error(f"Failed to register malicious font: {e}")
            raise
    
    def create_question_document(self):
        """
        Create a simple question document where only "AWS" uses the malicious font.
        
        Returns:
            str: Path to the created PDF file
        """
        # Create timestamp for unique filename
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"output/pdfs/question_{timestamp}.pdf"
        
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Create the PDF
        c = canvas.Canvas(output_path, pagesize=letter)
        width, height = letter
        
        # Position text at the top of the page
        y_position = height - 100
        x_start = 50
        
        # Create the question with mixed fonts
        # Start with normal font
        c.setFont("Helvetica", 18)
        question_start = "What is the full form of "
        
        # Draw the first part of the question
        c.drawString(x_start, y_position, question_start)
        
        # Calculate the width of the first part to position "AWS" right after it
        text_width = c.stringWidth(question_start, "Helvetica", 18)
        
        # Use malicious font for "AWS" - position it right after the previous text
        c.setFont(self.font_name, 18)
        c.drawString(x_start + text_width, y_position, "AWS")
        
        # Continue with normal font for the question mark - position it right after "AWS"
        c.setFont("Helvetica", 18)
        aws_width = c.stringWidth("AWS", self.font_name, 18)
        c.drawString(x_start + text_width + aws_width, y_position, "?")
        
        c.save()
        logger.info(f"Question document created: {output_path}")
        return output_path
    
    def create_all_documents(self):
        """
        Create all demonstration documents.
        
        Returns:
            list: List of created PDF file paths
        """
        created_files = []
        
        try:
            # Create the question document
            question_pdf = self.create_question_document()
            if question_pdf:
                created_files.append(question_pdf)
                logger.info(f"✓ Created Question Document: {question_pdf}")
            
            return created_files
            
        except Exception as e:
            logger.error(f"Error creating documents: {e}")
            return []

def create_all_documents():
    """
    Create all demonstration documents using the malicious font.
    
    Returns:
        list: List of created PDF file paths
    """
    try:
        # Find the most recent malicious font
        fonts_dir = "output/fonts"
        if not os.path.exists(fonts_dir):
            logger.error(f"Fonts directory not found: {fonts_dir}")
            logger.info("Please run font_creator.py first to create a malicious font")
            return []
        
        # Find the most recent malicious font file
        font_files = [f for f in os.listdir(fonts_dir) if f.startswith("malicious_font_") and f.endswith(".ttf")]
        if not font_files:
            logger.error("No malicious font files found")
            logger.info("Please run font_creator.py first to create a malicious font")
            return []
        
        # Sort by timestamp and get the most recent
        font_files.sort(reverse=True)
        latest_font = os.path.join(fonts_dir, font_files[0])
        logger.info(f"Using malicious font: {latest_font}")
        
        # Create PDF generator
        generator = MaliciousPDFGenerator(latest_font)
        
        # Create all documents
        created_files = generator.create_all_documents()
        
        logger.info("=" * 60)
        logger.info("PDF GENERATION COMPLETE")
        logger.info("=" * 60)
        logger.info("Created documents:")
        for file_path in created_files:
            logger.info(f"  - {file_path}")
        logger.info("=" * 60)
        
        return created_files
        
    except Exception as e:
        logger.error(f"Error in create_all_documents: {e}")
        return []

if __name__ == "__main__":
    created_files = create_all_documents()
    if created_files:
        logger.info("✓ PDF generation completed successfully")
    else:
        logger.error("✗ PDF generation failed") 