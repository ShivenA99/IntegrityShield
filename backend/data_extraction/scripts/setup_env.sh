#!/bin/bash
# Shell script to set up .env file easily (Mac/Linux)
# This script should be run from the project root directory

cd "$(dirname "$0")/.."

echo "============================================================"
echo "        OpenAI API Key Setup for Mac/Linux"
echo "============================================================"
echo

# Check if .env already exists
if [ -f .env ]; then
    echo "[!] .env file already exists!"
    echo
    read -p "Do you want to overwrite it? (y/n): " OVERWRITE
    if [[ ! "$OVERWRITE" =~ ^[Yy]$ ]]; then
        echo "Setup cancelled."
        exit 0
    fi
fi

# Check if env.template exists
if [ ! -f env.template ]; then
    echo "[ERROR] env.template not found!"
    echo "Please make sure you're running this from the project root directory."
    echo "Current directory: $(pwd)"
    exit 1
fi

# Copy template to .env
echo "[1/3] Creating .env file..."
cp env.template .env
echo "      ✓ Done!"
echo

# Prompt for API key
echo "[2/3] Please enter your OpenAI API key:"
echo "      (Get it from: https://platform.openai.com/api-keys)"
echo
read -p "      API Key: " API_KEY

if [ -z "$API_KEY" ]; then
    echo
    echo "[WARNING] No API key entered. You'll need to edit .env manually."
    echo "          Open .env and add: OPENAI_API_KEY=your-key-here"
else
    echo
    echo "[3/3] Saving API key to .env..."
    echo "OPENAI_API_KEY=$API_KEY" > .env
    echo "      ✓ Done!"
fi

echo
echo "============================================================"
echo "                  Setup Complete!"
echo "============================================================"
echo
echo "Your .env file has been created."
echo
echo "Next steps:"
echo "  1. Install dependencies: pip install -r requirements.txt"
echo "  2. Test your setup:      python test_api_key.py"
echo "  3. Run the pipeline:     python main.py"
echo
echo "IMPORTANT: Never commit .env to git! (it's already in .gitignore)"
echo

# Make .env readable only by owner for security
chmod 600 .env 2>/dev/null

