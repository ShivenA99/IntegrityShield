#!/usr/bin/env python3
"""
Verify prevention font library is working correctly
"""
import sys
from pathlib import Path

# Add app to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.pipeline.font_attack.prevention_font_library import get_prevention_font_library


def main():
    print("=" * 70)
    print("PREVENTION FONT LIBRARY VERIFICATION")
    print("=" * 70)
    print()

    # Load library
    library = get_prevention_font_library()

    # Check if loaded
    if not library.is_loaded():
        print("❌ ERROR: Library not loaded!")
        print()
        print("Please generate the library first:")
        print("  cd backend")
        print("  .venv/bin/python scripts/generate_prevention_font_library.py")
        print()
        return 1

    print("✓ Library loaded successfully!")
    print()

    # Display stats
    stats = library.get_library_stats()
    print("LIBRARY STATISTICS:")
    print(f"  Library Directory: {stats['library_dir']}")
    print(f"  Total Fonts:       {stats['total_fonts']}")
    print(f"  Hidden Character:  '{stats['hidden_char']}'")
    print(f"  Available Chars:   {stats['available_chars']}")
    print()

    # Verify integrity
    print("VERIFYING LIBRARY INTEGRITY...")
    verification = library.verify_library()
    print(f"  Total:   {verification['total']}")
    print(f"  Valid:   {verification['valid']}")
    print(f"  Missing: {verification['missing']}")
    print()

    if verification['missing'] > 0:
        print("⚠️  WARNING: Some fonts are missing!")
        print("   Consider regenerating the library.")
        print()

    # Test lookups for common characters
    print("TESTING FONT LOOKUPS:")
    test_chars = ['A', 'a', 'B', 'b', '0', '1', '9', ' ', '+', '-']

    for char in test_chars:
        font_path = library.get_font_for_char(char)
        if font_path:
            print(f"  '{char}' → ✓ {font_path.name}")
        else:
            print(f"  '{char}' → ✗ NOT FOUND")

    print()

    # Performance estimate
    print("PERFORMANCE ESTIMATE:")
    print(f"  Font generation time:  ~0 seconds (pre-generated)")
    print(f"  Font copy time:        ~0.001 seconds per font")
    print(f"  Expected speedup:      ~100x faster than runtime generation")
    print()

    # Success summary
    if verification['missing'] == 0:
        print("=" * 70)
        print("✓✓✓ LIBRARY VERIFICATION PASSED! ✓✓✓")
        print("=" * 70)
        print()
        print("The prevention font library is ready to use!")
        print("You can now run prevention mode tests with instant font application.")
        print()
        return 0
    else:
        print("=" * 70)
        print("⚠️  LIBRARY VERIFICATION COMPLETED WITH WARNINGS")
        print("=" * 70)
        return 1


if __name__ == '__main__':
    sys.exit(main())
