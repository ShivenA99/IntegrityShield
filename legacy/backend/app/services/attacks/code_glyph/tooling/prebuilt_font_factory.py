#!/usr/bin/env python3
"""
Prebuilt Pair-Font Factory

Generates a library of single-pair mapping fonts for a given charset using a
specified base TTF (e.g., DejaVuSans.ttf). Each generated font maps exactly one
input codepoint (c_in) to the glyph of another codepoint (c_out). All other
mappings remain unchanged.

Output structure (for --charset v1/v2):
  demo/prebuilt_fonts/DejaVuSans/<preset>/
    DejaVuSans.ttf                  # copied base font for reference/registration
    map_U+XXXX_to_U+YYYY.ttf       # one file per (c_in -> c_out)

Usage examples:
  python prebuilt_font_factory.py --charset v1
  python prebuilt_font_factory.py --charset v2
  python prebuilt_font_factory.py --charset v2 --only-chars "AB CXYZxyz01234789/-_@$.:#"
  python prebuilt_font_factory.py --charset v1 --limit 50
  python prebuilt_font_factory.py --charset v1 --source-font demo/DejaVuSans.ttf --out-dir demo/prebuilt_fonts/DejaVuSans/v1
"""

import os
import sys
import shutil
import argparse
import logging
import copy
from typing import List

try:
    from fontTools.ttLib import TTFont
except ImportError:
    print("fontTools not installed. Install with: pip install fonttools")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def build_charset(name: str) -> List[str]:
    """Return list of characters for a named charset preset."""
    if name == "v1":
        # alpha_lower + alpha_upper + digits + space
        lowers = [chr(c) for c in range(ord('a'), ord('z') + 1)]
        uppers = [chr(c) for c in range(ord('A'), ord('Z') + 1)]
        digits = [chr(c) for c in range(ord('0'), ord('9') + 1)]
        space = [' ']
        return lowers + uppers + digits + space
    if name == "v2":
        # Printable ASCII 0x20-0x7E (space through tilde)
        return [chr(c) for c in range(0x20, 0x7F)]
    raise ValueError(f"Unknown charset preset: {name}")


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def get_best_cmap_table(tt: TTFont):
    cmap = tt.get('cmap')
    if not cmap:
        raise ValueError("Font does not contain a cmap table")
    # Prefer format 12 (UCS-4), then 4
    best = None
    for table in cmap.tables:
        if table.format in (12, 4):
            best = table
            if table.format == 12:
                break
    if best is None:
        best = cmap.tables[0]
    return best


def duplicate_glyph(tt: TTFont, source_glyph_name: str, new_glyph_name: str) -> None:
    """Duplicate a glyph outline and metrics under a new glyph name."""
    glyf = tt['glyf']
    hmtx = tt['hmtx']
    maxp = tt['maxp']

    if source_glyph_name not in glyf.glyphs:
        # Some fonts use .glyphs dict or item access
        if source_glyph_name not in glyf:
            raise KeyError(f"Glyph not found: {source_glyph_name}")

    # Copy glyph outline
    glyf[new_glyph_name] = copy.deepcopy(glyf[source_glyph_name])

    # Copy metrics
    if source_glyph_name in hmtx.metrics:
        hmtx.metrics[new_glyph_name] = hmtx.metrics[source_glyph_name]
    else:
        # Fallback: use a reasonable default if missing
        hmtx.metrics[new_glyph_name] = (600, 0)

    # Append to glyph order
    glyph_order = tt.getGlyphOrder()
    if new_glyph_name not in glyph_order:
        glyph_order.append(new_glyph_name)
        tt.setGlyphOrder(glyph_order)

    # Update glyph count
    if hasattr(maxp, 'numGlyphs'):
        maxp.numGlyphs = len(tt.getGlyphOrder())


def generate_pair_font(source_font_path: str, out_path: str, c_in: str, c_out: str) -> bool:
    """Generate a font mapping exactly c_in -> glyph(c_out), via duplicated glyph to preserve ToUnicode."""
    try:
        # Try several fontNumber indices in case of collections
        tt = None
        for fn in range(6):
            try:
                tt = TTFont(source_font_path, fontNumber=fn)
                break
            except Exception:
                if fn == 5:
                    raise
                continue
        assert tt is not None

        table = get_best_cmap_table(tt)
        cmap = table.cmap

        in_code = ord(c_in)
        out_code = ord(c_out)

        if out_code not in cmap:
            logger.warning(f"Skip: output code U+{out_code:04X} not in cmap (in={c_in!r}, out={c_out!r})")
            tt.close()
            return False

        # Resolve glyph name for target
        target_glyph_name = cmap[out_code]
        new_glyph_name = f"{target_glyph_name}.ALT_for_U+{in_code:04X}"

        # Duplicate glyph and metrics
        duplicate_glyph(tt, target_glyph_name, new_glyph_name)

        # Map input codepoint to the duplicated glyph name; DO NOT change out_code mapping
        cmap[in_code] = new_glyph_name

        ensure_dir(os.path.dirname(out_path))
        tt.save(out_path)
        tt.close()
        return True
    except Exception as e:
        logger.error(f"Failed to generate pair font for {c_in!r} -> {c_out!r}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Prebuilt Pair-Font Factory")
    parser.add_argument("--charset", default="v1", help="Charset preset: v1 = alpha_lower+alpha_upper+digits+space; v2 = printable ASCII (space..~); v3 = zero-width strategy core")
    parser.add_argument("--source-font", default="demo/DejaVuSans.ttf", help="Path to base TTF font")
    parser.add_argument("--out-dir", default="demo/prebuilt_fonts/DejaVuSans/v1", help="Output directory for prebuilt fonts")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of pairs for quick builds (0 = no limit)")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing pair fonts")
    parser.add_argument("--only-chars", default="", help="If provided, build using exactly these characters instead of the preset charset (v1/v2)")
    args = parser.parse_args()

    # v3 special handling (asymmetric pairs)
    if args.charset == 'v3':
        zw_inputs = ['\u200B']  # ZERO WIDTH SPACE
        vis_chars = [chr(c) for c in range(0x20, 0x7F)]  # printable ASCII
        if not os.path.exists(args.source_font):
            logger.error(f"Source font not found: {args.source_font}")
            sys.exit(1)
        # Copy base font into out-dir
        ensure_dir(args.out_dir)
        base_copy_path = os.path.join(args.out_dir, os.path.basename(args.source_font))
        if not os.path.exists(base_copy_path):
            shutil.copy2(args.source_font, base_copy_path)
            logger.info(f"Copied base font to: {base_copy_path}")
        else:
            logger.info(f"Base font already present at: {base_copy_path}")
        success = 0
        # Group 1: U+200B -> visible printable
        for c_out in vis_chars:
            out_name = f"map_U+200B_to_U+{ord(c_out):04X}.ttf"
            out_path = os.path.join(args.out_dir, out_name)
            if os.path.exists(out_path) and not args.overwrite:
                success += 1
            else:
                if generate_pair_font(args.source_font, out_path, '\u200B', c_out):
                    success += 1
            if args.limit and success >= args.limit:
                break
        # Group 2: visible printable -> U+200B (hide)
        if not args.limit or success < args.limit:
            for c_in in vis_chars:
                out_name = f"map_U+{ord(c_in):04X}_to_U+200B.ttf"
                out_path = os.path.join(args.out_dir, out_name)
                if os.path.exists(out_path) and not args.overwrite:
                    success += 1
                else:
                    if generate_pair_font(args.source_font, out_path, c_in, '\u200B'):
                        success += 1
                if args.limit and success >= args.limit:
                    break
        total_pairs = len(vis_chars) * 2
        logger.info(f"Completed v3 build. Requested pairs: ~{total_pairs}")
        logger.info(f"Generated OK: {success}")
        return

    # Resolve charset for v1/v2 or custom
    if args.only_chars:
        # Use provided characters literally (no deduped order changes)
        charset = list(dict.fromkeys(list(args.only_chars)))
        logger.info(f"Using custom character set of length {len(charset)} from --only-chars")
    else:
        charset = build_charset(args.charset)
        logger.info(f"Using preset charset '{args.charset}' with length {len(charset)}")

    if not os.path.exists(args.source_font):
        logger.error(f"Source font not found: {args.source_font}")
        sys.exit(1)

    # Copy base font into out-dir
    ensure_dir(args.out_dir)
    base_copy_path = os.path.join(args.out_dir, os.path.basename(args.source_font))
    if not os.path.exists(base_copy_path):
        shutil.copy2(args.source_font, base_copy_path)
        logger.info(f"Copied base font to: {base_copy_path}")
    else:
        logger.info(f"Base font already present at: {base_copy_path}")

    success = 0
    for i, c_in in enumerate(charset):
        for j, c_out in enumerate(charset):
            if c_in == c_out:
                continue
            out_name = f"map_U+{ord(c_in):04X}_to_U+{ord(c_out):04X}.ttf"
            out_path = os.path.join(args.out_dir, out_name)
            if os.path.exists(out_path) and not args.overwrite:
                success += 1
                if args.limit and success >= args.limit:
                    break
                continue
            if generate_pair_font(args.source_font, out_path, c_in, c_out):
                success += 1
            if args.limit and success >= args.limit:
                break
        if args.limit and success >= args.limit:
            break

    total_pairs = len(charset) * len(charset) - len(charset)
    logger.info(f"Completed. Requested pairs (excluding identity): ~{total_pairs}")
    logger.info(f"Generated OK: {success}")


if __name__ == "__main__":
    main() 