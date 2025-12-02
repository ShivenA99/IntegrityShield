#!/usr/bin/env python3
"""
Generate comprehensive pre-built font library for prevention mode
Covers extended Unicode ranges for universal character support
Maps single hidden character 'a' to all possible visual characters
"""
import sys
import json
from pathlib import Path

# Add app to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.pipeline.font_attack.font_builder import FontAttackBuilder
from app.services.pipeline.font_attack.chunking import AttackPosition


def generate_comprehensive_character_set():
    """
    Generate comprehensive character set covering:
    - All printable ASCII (32-126)
    - Extended Latin (common accented characters)
    - Greek alphabet (upper and lower)
    - Mathematical operators and symbols
    - Common typographic symbols
    - Superscripts and subscripts
    """
    chars = set()

    # 1. All printable ASCII (32-126)
    for code in range(32, 127):
        chars.add(chr(code))

    # 2. Extended Latin - Accented characters (Latin-1 Supplement)
    for code in range(0xC0, 0x100):  # À-ÿ
        chars.add(chr(code))

    # 3. Extended Latin - Additional (Latin Extended-A)
    common_extended = [
        'Ā', 'ā', 'Ă', 'ă', 'Ą', 'ą', 'Ć', 'ć', 'Č', 'č',
        'Ď', 'ď', 'Đ', 'đ', 'Ē', 'ē', 'Ė', 'ė', 'Ę', 'ę',
        'Ě', 'ě', 'Ğ', 'ğ', 'Ī', 'ī', 'İ', 'ı', 'Ł', 'ł',
        'Ń', 'ń', 'Ň', 'ň', 'Ō', 'ō', 'Ő', 'ő', 'Œ', 'œ',
        'Ř', 'ř', 'Ś', 'ś', 'Š', 'š', 'Ș', 'ș', 'Ț', 'ț',
        'Ū', 'ū', 'Ů', 'ů', 'Ű', 'ű', 'Ź', 'ź', 'Ž', 'ž', 'Ż', 'ż'
    ]
    chars.update(common_extended)

    # 4. Greek alphabet (complete)
    greek_lower = 'αβγδεζηθικλμνξοπρστυφχψω'
    greek_upper = 'ΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩ'
    chars.update(greek_lower)
    chars.update(greek_upper)

    # 5. Mathematical operators
    math_operators = [
        # Basic operators
        '±', '×', '÷', '∓', '∔', '∕', '∖', '∗', '∘', '∙', '√', '∛', '∜',
        # Relations
        '≈', '≠', '≡', '≢', '≤', '≥', '≦', '≧', '≨', '≩', '≪', '≫',
        '⊂', '⊃', '⊆', '⊇', '⊈', '⊉', '⊊', '⊋',
        # Calculus
        '∂', '∇', '∆', '∫', '∬', '∭', '∮', '∯', '∰', '∱', '∲', '∳',
        # Set theory
        '∈', '∉', '∋', '∌', '∩', '∪', '∅', '∞',
        # Logic
        '∀', '∃', '∄', '∧', '∨', '¬', '⊕', '⊗',
        # Arrows
        '←', '→', '↑', '↓', '↔', '↕', '⇐', '⇒', '⇔', '⇕',
        # Summation/Product
        '∑', '∏', '∐', '⋀', '⋁', '⋂', '⋃',
        # Other
        '∝', '∟', '∠', '∡', '∢', '⊥', '∥', '∦', '≅', '≃'
    ]
    chars.update(math_operators)

    # 6. Superscripts and subscripts
    superscripts = '⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱ'
    subscripts = '₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₒₓₔₕₖₗₘₙₚₛₜ'
    chars.update(superscripts)
    chars.update(subscripts)

    # 7. Common typographic symbols
    typography = [
        '–', '—', ''', ''', '"', '"', '‚', '„', '†', '‡',
        '•', '‣', '⁃', '◦', '‰', '‱', '′', '″', '‴', '※',
        '§', '¶', '©', '®', '™', '℠', '№', '℃', '℉', '℗'
    ]
    chars.update(typography)

    # 8. Currency symbols
    currency = '¤¢£¥€₹₽₩₪₫฿₴₦₨₱₡₵₸₺₼₾'
    chars.update(currency)

    # 9. Common fractions
    fractions = '¼½¾⅓⅔⅕⅖⅗⅘⅙⅚⅛⅜⅝⅞'
    chars.update(fractions)

    # 10. Box drawing and blocks (useful for tables)
    box_drawing = [
        '─', '━', '│', '┃', '┌', '┐', '└', '┘', '├', '┤', '┬', '┴', '┼',
        '═', '║', '╔', '╗', '╚', '╝', '╠', '╣', '╦', '╩', '╬',
        '▀', '▄', '█', '▌', '▐', '░', '▒', '▓', '■', '□', '▪', '▫'
    ]
    chars.update(box_drawing)

    # 11. Common diacritics (combining characters)
    # Note: These might need special handling, but include them
    diacritics = '̀́̂̃̄̅̆̇̈̉̊̋̌̍̎̏'
    # Skip combining diacritics for now as they need special handling

    # 12. Arrows (extended)
    arrows = '←→↑↓↔↕↖↗↘↙⇄⇅⇆⇇⇈⇉⇊⇋⇌⇍⇎⇏⇐⇑⇒⇓⇔⇕⇖⇗⇘⇙⇚⇛⇜⇝⇞⇟'
    chars.update(arrows)

    # 13. Geometric shapes
    shapes = '○●◯◎◉◊◇◆◈◌◍◐◑◒◓◔◕◖◗★☆☐☑☒☓☼☽☾☿'
    chars.update(shapes)

    # Filter out multi-character strings and convert to sorted list
    single_chars = [c for c in chars if len(c) == 1]
    return sorted(single_chars)


def generate_comprehensive_prevention_library(
    output_dir: Path,
    hidden_char: str = 'a',
    base_font: str = "Roboto-Regular"
):
    """
    Generate comprehensive prevention font library with extended Unicode support

    Args:
        output_dir: Directory to store generated fonts
        hidden_char: Single character to use in hidden layer (default: 'a')
        base_font: Base font to use (default: Roboto-Regular)
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate comprehensive character set
    visual_chars = generate_comprehensive_character_set()

    print("=" * 80)
    print("COMPREHENSIVE PREVENTION FONT LIBRARY GENERATION")
    print("=" * 80)
    print(f"  Hidden character: '{hidden_char}'")
    print(f"  Visual characters: {len(visual_chars)}")
    print(f"  Output directory: {output_dir}")
    print()
    print("Character coverage:")
    print(f"  • All printable ASCII: ✓")
    print(f"  • Extended Latin (accented): ✓")
    print(f"  • Greek alphabet: ✓")
    print(f"  • Mathematical symbols: ✓")
    print(f"  • Currency symbols: ✓")
    print(f"  • Typography symbols: ✓")
    print(f"  • Box drawing & shapes: ✓")
    print(f"  • Arrows & operators: ✓")
    print(f"  • Superscripts & subscripts: ✓")
    print("=" * 80)
    print()

    # Find base font path
    base_font_dir = Path(__file__).parent.parent / "resources" / "fonts"
    base_font_path = base_font_dir / f"{base_font}.ttf"

    if not base_font_path.exists():
        for ext in ['.otf', '.woff']:
            alt_path = base_font_dir / f"{base_font}{ext}"
            if alt_path.exists():
                base_font_path = alt_path
                break

    if not base_font_path.exists():
        raise FileNotFoundError(f"Base font not found: {base_font_path}")

    print(f"Using base font: {base_font_path.name}")
    print()

    # Initialize font builder and get glyph lookup
    builder = FontAttackBuilder(base_font_path)
    glyph_lookup = builder.glyph_lookup

    # Generate metadata
    metadata = {
        'version': '2.0',
        'hidden_char': hidden_char,
        'base_font': str(base_font_path),
        'total_chars': len(visual_chars),
        'visual_chars': ''.join(visual_chars),
        'fonts': {}
    }

    # Generate fonts for each visual character
    generated_count = 0
    failed_count = 0

    for idx, visual_char in enumerate(visual_chars):
        # Create safe filename
        if visual_char == ' ':
            safe_name = 'space'
        elif visual_char in '/\\:*?"<>|':
            safe_name = f'u{ord(visual_char):04x}'
        else:
            # Try to use the character, fall back to unicode hex
            try:
                safe_name = visual_char
                # Test if it's filesystem safe
                test_path = output_dir / f"test_{safe_name}.tmp"
                test_path.touch()
                test_path.unlink()
            except:
                safe_name = f'u{ord(visual_char):04x}'

        font_filename = f"pfa{idx:04d}.ttf"  # Shorter names for filesystem
        font_path = output_dir / font_filename

        # Generate font
        try:
            # Skip multi-character strings (shouldn't happen after filtering)
            # Also validate that ord() will work (catches surrogate pairs and grapheme clusters)
            if len(visual_char) != 1:
                failed_count += 1
                print(f"  ⚠️  Skipping multi-char [{idx}]: {repr(visual_char)}")
                continue

            # Additional validation: ensure ord() can process this character
            try:
                char_code = ord(visual_char)
            except TypeError:
                failed_count += 1
                print(f"  ⚠️  Skipping invalid char [{idx}]: {repr(visual_char)} (ord() failed)")
                continue

            # Get glyph information for the visual character
            try:
                visual_glyph_name = glyph_lookup.glyph_name(visual_char)
                visual_glyph_width = glyph_lookup.glyph_width(visual_char)
            except KeyError:
                failed_count += 1
                print(f"  ⚠️  Skipping char [{idx}] '{visual_char}': Glyph not found in font")
                continue

            # Create AttackPosition with proper glyph names
            position = AttackPosition(
                index=idx,
                hidden_char=hidden_char,
                visual_text=visual_char,
                glyph_names=(visual_glyph_name,),  # Tuple with the visual glyph name
                advance_width=visual_glyph_width
            )

            builder._write_position_font(position, font_path)

            # Store metadata
            metadata['fonts'][visual_char] = {
                'filename': font_filename,
                'index': idx,
                'unicode': f'U+{char_code:04X}',
                'category': categorize_char(visual_char)
            }

            generated_count += 1

            # Progress indicator
            if (idx + 1) % 50 == 0:
                print(f"  [{idx + 1}/{len(visual_chars)}] Generated {generated_count} fonts, {failed_count} failed...")

        except Exception as e:
            failed_count += 1
            # Safe unicode representation for error messages
            try:
                unicode_repr = f'U+{ord(visual_char):04X}'
            except (TypeError, ValueError):
                unicode_repr = repr(visual_char)
            print(f"  ⚠️  Failed [{idx}] '{visual_char}' ({unicode_repr}): {str(e)[:50]}")
            continue

    # Save metadata
    metadata_path = output_dir / "metadata.json"
    with open(metadata_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    # Save character map for quick reference
    charmap_path = output_dir / "character_map.txt"
    with open(charmap_path, 'w', encoding='utf-8') as f:
        f.write("Prevention Font Library - Character Map\n")
        f.write("=" * 80 + "\n\n")
        for visual_char, info in metadata['fonts'].items():
            f.write(f"{info['index']:4d}  {info['filename']:20s}  '{visual_char}'  {info['unicode']:8s}  {info['category']}\n")

    print()
    print("=" * 80)
    print("✓ COMPREHENSIVE LIBRARY GENERATION COMPLETE!")
    print("=" * 80)
    print(f"  Successfully generated: {generated_count}/{len(visual_chars)} fonts")
    print(f"  Failed: {failed_count}")
    print(f"  Success rate: {generated_count/len(visual_chars)*100:.1f}%")
    print(f"  Metadata saved to: {metadata_path.name}")
    print(f"  Character map: {charmap_path.name}")
    print("=" * 80)

    return metadata


def categorize_char(char: str) -> str:
    """Categorize character for metadata"""
    code = ord(char)
    if 32 <= code <= 126:
        if char.isalpha():
            return "ASCII Letter"
        elif char.isdigit():
            return "ASCII Digit"
        else:
            return "ASCII Symbol"
    elif 0xC0 <= code <= 0xFF:
        return "Latin Extended"
    elif char in 'αβγδεζηθικλμνξοπρστυφχψωΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩ':
        return "Greek"
    elif char in '±×÷∑∏∫∂∇√∞≈≠≤≥⊂⊃∈∉∀∃':
        return "Math"
    elif char in '€£¥$¢₹₽':
        return "Currency"
    elif char in '←→↑↓↔⇐⇒⇔':
        return "Arrow"
    elif char in '○●◆★☆■□':
        return "Shape"
    else:
        return "Other"


if __name__ == '__main__':
    # Output directory
    output_dir = Path(__file__).parent.parent / "data" / "font_library" / "prevention"

    # Generate comprehensive library
    generate_comprehensive_prevention_library(output_dir)
