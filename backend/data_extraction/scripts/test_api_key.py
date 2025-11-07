"""
Simple script to test if your OpenAI API key is loaded correctly from .env
"""
import os
import sys
from pathlib import Path

# Add parent directory to path to import config
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_env_file_exists():
    """Check if .env file exists"""
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        print("✓ .env file found")
        return True
    else:
        print("✗ .env file not found")
        print("  → Copy .env.template to .env and add your API key")
        return False

def test_api_key_loaded():
    """Check if API key is loaded from .env"""
    # Import after .env check
    from config import OPENAI_API_KEY
    
    if not OPENAI_API_KEY:
        print("✗ API key is empty")
        print("  → Open .env and set OPENAI_API_KEY=your-key-here")
        return False
    elif OPENAI_API_KEY == "your-api-key-here":
        print("✗ API key is still the placeholder value")
        print("  → Replace 'your-api-key-here' with your actual API key")
        return False
    elif not OPENAI_API_KEY.startswith("sk-"):
        print("⚠ API key doesn't start with 'sk-' (may be invalid)")
        print(f"  → Current value starts with: {OPENAI_API_KEY[:5]}...")
        return False
    else:
        print("✓ API key is loaded")
        print(f"  → Key starts with: {OPENAI_API_KEY[:10]}...")
        print(f"  → Key length: {len(OPENAI_API_KEY)} characters")
        return True

def test_openai_import():
    """Check if OpenAI library is installed"""
    try:
        import openai
        print("✓ OpenAI library installed")
        return True
    except ImportError:
        print("✗ OpenAI library not installed")
        print("  → Run: pip install -r requirements.txt")
        return False

def test_dotenv_import():
    """Check if python-dotenv is installed"""
    try:
        import dotenv
        print("✓ python-dotenv library installed")
        return True
    except ImportError:
        print("✗ python-dotenv not installed")
        print("  → Run: pip install python-dotenv")
        return False

def main():
    print("="*60)
    print("OpenAI API Key Configuration Test")
    print("="*60)
    print()
    
    # Run all tests
    tests = [
        ("python-dotenv", test_dotenv_import),
        (".env file", test_env_file_exists),
        ("API key", test_api_key_loaded),
        ("OpenAI library", test_openai_import),
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n[Test: {test_name}]")
        try:
            result = test_func()
            results.append(result)
        except Exception as e:
            print(f"✗ Error: {e}")
            results.append(False)
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    passed = sum(results)
    total = len(results)
    
    if passed == total:
        print(f"✓ All tests passed ({passed}/{total})")
        print("\n🎉 You're ready to use the pipeline with OpenAI!")
        print("\nRun: python main.py")
    else:
        print(f"⚠ {passed}/{total} tests passed")
        print("\n📝 Follow the instructions above to fix the issues.")
        print("\nFor detailed setup instructions, see: SETUP_API_KEY.md")

if __name__ == "__main__":
    main()

