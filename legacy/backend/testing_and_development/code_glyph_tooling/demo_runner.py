#!/usr/bin/env python3
"""
Quick Demo Runner for Malicious Font Injection Attack
Simple script to run the complete demonstration.
"""

import os
import sys
import subprocess
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def run_demo():
    """
    Run the complete malicious font injection attack demonstration.
    """
    logger.info("🚀 Starting Malicious Font Injection Attack Demo")
    logger.info("=" * 60)
    
    try:
        # Check if virtual environment exists
        if not os.path.exists("new_venv"):
            logger.error("Virtual environment not found. Please run setup first.")
            return False
        
        # Activate virtual environment and run main script
        cmd = "source new_venv/bin/activate && python main.py"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info("✅ Demo completed successfully!")
            logger.info("📁 Check the generated files:")
            logger.info("   - malicious_font.ttf")
            logger.info("   - malicious_document.pdf")
            logger.info("   - question_document.pdf")
            logger.info("   - news_article.pdf")
            return True
        else:
            logger.error("❌ Demo failed!")
            logger.error(f"Error: {result.stderr}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Demo failed with exception: {e}")
        return False

def setup_demo():
    """
    Setup the demo environment.
    """
    logger.info("🔧 Setting up demo environment...")
    
    try:
        # Create virtual environment
        if not os.path.exists("new_venv"):
            logger.info("Creating virtual environment...")
            subprocess.run("python3 -m venv new_venv", shell=True, check=True)
        
        # Install dependencies
        logger.info("Installing dependencies...")
        cmd = "source new_venv/bin/activate && pip install fontTools reportlab"
        subprocess.run(cmd, shell=True, check=True)
        
        logger.info("✅ Setup completed successfully!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Setup failed: {e}")
        return False

def main():
    """
    Main function to run the demo.
    """
    if len(sys.argv) > 1 and sys.argv[1] == "setup":
        return setup_demo()
    else:
        return run_demo()

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 