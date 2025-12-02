#!/usr/bin/env python3
"""
Generate pre-built font library for prevention mode
Maps single hidden character 'a' to all possible visual characters
This enables instant font reuse without runtime generation
"""
import sys
import json
from pathlib import Path

# Add app to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.pipeline.font_attack.font_builder import FontAttackBuilder
from app.services.pipeline.font_attack.chunking import AttackPosition


def generate_prevention_font_library(
    output_dir: Path,
    hidden_char: str = 'a',
    base_font: str = "Roboto-Regular"
):
    """
    Pre-generate font library for prevention mode

    Args:
        output_dir: Directory to store generated fonts
        hidden_char: Single character to use in hidden layer (default: 'a')
        base_font: Base font to use (default: ComputerModern)
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Define all visual characters we might need
    # Include: letters, numbers, common symbols, Greek letters, math symbols
    visual_chars = (
        # Uppercase and lowercase letters
        'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
        # Numbers
        '0123456789'
        # Common punctuation and symbols
        '.,;:!?\'"()-[]{}+=*/<>@#$%^&_|\\~`'
        # Space
        ' '
        # Greek letters (common in math)
        'αβγδεζηθικλμνξοπρστυφχψω'
        'ΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩ'
        # Math symbols
        '∑∏∫∂∇√∞≈≠≤≥±×÷'
    )

    # Remove duplicates and sort
    visual_chars = ''.join(sorted(set(visual_chars)))

    print(f"Generating prevention font library...")
    print(f"  Hidden character: '{hidden_char}'")
    print(f"  Visual characters: {len(visual_chars)}")
    print(f"  Output directory: {output_dir}")
    print()

    # Find base font path in resources directory
    base_font_dir = Path(__file__).parent.parent / "resources" / "fonts"
    base_font_path = base_font_dir / f"{base_font}.ttf"

    if not base_font_path.exists():
        # Try alternative extensions
        for ext in ['.otf', '.woff']:
            alt_path = base_font_dir / f"{base_font}{ext}"
            if alt_path.exists():
                base_font_path = alt_path
                break

    if not base_font_path.exists():
        raise FileNotFoundError(f"Base font not found: {base_font_path}")

    print(f"Using base font: {base_font_path}")
    print()

    # Initialize font builder
    builder = FontAttackBuilder(base_font_path)

    # Generate metadata
    metadata = {
        'hidden_char': hidden_char,
        'base_font': str(base_font_path),
        'visual_chars': visual_chars,
        'fonts': {}
    }

    # Generate fonts for each visual character
    generated_count = 0
    for idx, visual_char in enumerate(visual_chars):
        # Create safe filename
        if visual_char == ' ':
            safe_name = 'space'
        elif visual_char in '/\\:*?"<>|':
            safe_name = f'unicode_{ord(visual_char)}'
        else:
            safe_name = visual_char

        font_filename = f"hidden_{hidden_char}_visual_{safe_name}.ttf"
        font_path = output_dir / font_filename

        # Create AttackPosition for this mapping
        position = AttackPosition(
            index=idx,
            hidden_char=hidden_char,
            visual_text=visual_char,
            glyph_names=[],  # Will be populated by builder
            advance_width=500.0  # Standard width, can be adjusted
        )

        # Generate font
        try:
            builder._write_position_font(position, font_path)

            # Store metadata
            metadata['fonts'][visual_char] = {
                'filename': font_filename,
                'path': str(font_path),
                'hidden_char': hidden_char,
                'visual_char': visual_char,
                'index': idx
            }

            generated_count += 1

            if (idx + 1) % 10 == 0:
                print(f"  Generated {idx + 1}/{len(visual_chars)} fonts...")

        except Exception as e:
            print(f"  ⚠️  Failed to generate font for '{visual_char}': {e}")
            continue

    # Save metadata
    metadata_path = output_dir / "metadata.json"
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)

    print()
    print("=" * 60)
    print(f"✓ Font library generation complete!")
    print(f"  Successfully generated: {generated_count}/{len(visual_chars)} fonts")
    print(f"  Metadata saved to: {metadata_path}")
    print("=" * 60)

    return metadata


if __name__ == '__main__':
    # Default output directory
    output_dir = Path(__file__).parent.parent / "data" / "font_library" / "prevention"

    # Generate library
    generate_prevention_font_library(output_dir)
