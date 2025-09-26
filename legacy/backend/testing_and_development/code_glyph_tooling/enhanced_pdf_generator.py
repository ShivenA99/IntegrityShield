#!/usr/bin/env python3
"""
Enhanced PDF Generator for Malicious Font Pipeline
Handles PDF generation with multiple malicious fonts applied to specific positions.
"""

import os
import sys
import datetime
import logging
from typing import List, Dict, Optional
import fitz  # PyMuPDF

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def _sanitize_for_filename(text: str, max_len: int = 80) -> str:
    """Sanitize arbitrary text for safe filename usage.
    - Keep [A-Za-z0-9-_.]
    - Convert spaces to '_'
    - Encode all other characters as U+XXXX
    - Truncate to max_len
    """
    safe_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")
    out = []
    for ch in text:
        if ch in safe_chars:
            out.append(ch)
        elif ch == ' ':
            out.append('_')
        else:
            out.append(f"U+{ord(ch):04X}")
    result = ''.join(out)
    if len(result) > max_len:
        result = result[:max_len]
    return result

def _assign_length_mismatch(input_entity: str, output_entity: str, before: str, after: str) -> Dict:
    """Assign Tier A (space-swap) handling for length mismatch.
    Zero-width mode: do not consume visible spaces.
    - If output longer: create synthetic zero-width slots appended right after the entity and map U+200B → extra visuals
    - If output shorter: mark surplus input indices to hide by mapping them to U+200B
    Returns dict with keys: entity_pairs, hide_indices, zw_append (list of extra visual chars)
    """
    n = min(len(input_entity), len(output_entity))
    entity_pairs = [(i, input_entity[i], output_entity[i]) for i in range(n)]
    hide_indices = []
    zw_append: List[str] = []

    if len(output_entity) > len(input_entity):
        zw_append = list(output_entity[n:])
    elif len(output_entity) < len(input_entity):
        # Hide surplus input chars by rendering them as zero-width
        hide_indices = list(range(n, len(input_entity)))

    return {
        "entity_pairs": entity_pairs,
        "hide_indices": hide_indices,
        "zw_append": zw_append,
    }

class EnhancedPDFGenerator:
    """
    Generates PDFs with multiple malicious fonts applied to specific positions.
    """
    
    def __init__(self):
        self.registered_fonts = {}
        self.font_configs = []
        # cache for prebuilt pair-fonts by key (e.g., "U+0041_to_U+0042")
        self.prebuilt_font_cache: Dict[str, str] = {}
        self.base_fontname: Optional[str] = None
        self.base_font_obj: Optional[fitz.Font] = None
        # cache of fitz.Font objects for pair fonts
        self._pair_font_objs: Dict[str, fitz.Font] = {}
    
    def register_fonts(self, font_configs: List[Dict]) -> None:
        """
        Register multiple malicious fonts.
        
        Args:
            font_configs (List[Dict]): List of font configurations
        """
        self.font_configs = font_configs
        
        logger.info("=" * 60)
        logger.info("🎨 REGISTERING MALICIOUS FONTS")
        logger.info("=" * 60)
        logger.info(f"📋 Total font configurations to register: {len(font_configs)}")
        
        for i, config in enumerate(font_configs, 1):
            logger.info(f"")
            logger.info(f"🔧 Registering font {i}/{len(font_configs)}:")
            logger.info(f"  📝 Font name: {config['font_name']}")
            logger.info(f"  📁 Font path: {config['font_path']}")
            logger.info(f"  🎯 Character mappings: {config['character_mappings']}")
            logger.info(f"  📍 Apply positions: {config['apply_positions']}")
            logger.info(f"  ⭐ Priority: {config['priority']}")
            logger.info(f"  📄 Description: {config['description']}")
            
            try:
                font_path = config["font_path"]
                font_name = config["font_name"]
                
                # Check if font file exists
                if not os.path.exists(font_path):
                    logger.error(f"  ❌ Font file not found: {font_path}")
                    continue
                
                logger.info(f"  ✅ Font file exists")
                logger.info(f"  ✅ Font {font_name} ready for use with PyMuPDF")
                
            except Exception as e:
                logger.error(f"  ❌ Failed to process font {config['font_name']}: {e}")
                logger.error(f"     Error details: {type(e).__name__}: {str(e)}")
        
        logger.info(f"")
        logger.info(f"✅ Successfully prepared {len(font_configs)} font(s) for PyMuPDF")
        logger.info("=" * 60)
    
    def create_document(self, input_string: str, input_entity: str, output_entity: str, run_id: str) -> str:
        """
        Create a PDF document with malicious fonts applied to the target entity.
        
        Args:
            input_string (str): The complete input text
            input_entity (str): The entity to attack
            output_entity (str): The desired visual output
            run_id (str): Unique run identifier
            
        Returns:
            str: Path to the created PDF file
        """
        logger.info(f"📄 CREATING PDF DOCUMENT")
        logger.info(f"============================================================")
        logger.info(f"📝 Input string: '{input_string}'")
        logger.info(f"🎯 Input entity: '{input_entity}'")
        logger.info(f"🎯 Output entity: '{output_entity}'")
        logger.info(f"🆔 Run ID: {run_id}")
        
        # Create output directory
        pdfs_dir = f"output/runs/{run_id}/pdfs"
        logger.info(f"📁 Creating PDF directory: {pdfs_dir}")
        os.makedirs(pdfs_dir, exist_ok=True)
        logger.info(f"✅ PDF directory created")
        
        # Generate PDF filename
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_in = _sanitize_for_filename(input_entity)
        safe_out = _sanitize_for_filename(output_entity)
        pdf_filename = f"{safe_in}_{safe_out}_{timestamp}.pdf"
        pdf_path = os.path.join(pdfs_dir, pdf_filename)
        logger.info(f"📄 PDF filename: {pdf_filename}")
        logger.info(f"📄 Full PDF path: {pdf_path}")
        
        # Create the PDF with PyMuPDF
        logger.info(f"🔧 Creating PyMuPDF document...")
        doc = fitz.open()
        page = doc.new_page()
        logger.info(f"✅ PyMuPDF document created")
        
        # Insert fonts into the document
        logger.info(f"🎨 Inserting fonts into document...")
        for config in self.font_configs:
            font_path = config["font_path"]
            font_name = config["font_name"]
            try:
                page.insert_font(fontname=font_name, fontfile=font_path)
                logger.info(f"  ✅ Inserted font: {font_name}")
            except Exception as e:
                logger.error(f"  ❌ Failed to insert font {font_name}: {e}")
        
        # Position text at the top of the page
        y_position = 50
        x_start = 20  # Reduced left margin
        logger.info(f"📍 Text position: x={x_start}, y={y_position}")
        
        # Apply fonts to the text
        logger.info(f"🎨 Applying fonts to text...")
        self._apply_fonts_to_text(page, input_string, input_entity, x_start, y_position)
        
        logger.info(f"💾 Saving PDF...")
        doc.save(pdf_path)
        doc.close()
        logger.info(f"✅ PDF created successfully: {pdf_path}")
        logger.info(f"============================================================")
        return pdf_path
    
    def _apply_fonts_to_text(self, page, text: str, target_entity: str, x_start: float, y_position: float) -> None:
        """
        Apply malicious fonts to specific positions in the text.
        
        Args:
            page: The PDF page object
            text (str): The complete text
            target_entity (str): The entity to apply fonts to
            x_start (float): Starting x position
            y_position (float): Y position for text
        """
        # Find the target entity in the text
        entity_start = text.find(target_entity)
        if entity_start == -1:
            logger.error(f"Target entity '{target_entity}' not found in text")
            return
        
        entity_end = entity_start + len(target_entity)
        
        # Split text into parts
        before_entity = text[:entity_start]
        after_entity = text[entity_end:]
        
        current_x = x_start
        
        # Draw text before the entity with proper spacing
        if before_entity:
            page.insert_text((current_x, y_position), before_entity, fontsize=18)
            # Use more accurate character width estimation
            current_x += len(before_entity) * 10  # Better character width estimate
        
        # Apply fonts to the entity
        current_x = self._apply_fonts_to_entity(page, target_entity, current_x, y_position)
        
        # Draw text after the entity
        if after_entity:
            page.insert_text((current_x, y_position), after_entity, fontsize=18)
    
    def _apply_fonts_to_entity(self, page, entity: str, x_start: float, y_position: float) -> float:
        """
        Apply malicious fonts to each character in the entity.
        
        Args:
            page: The PDF page object
            entity (str): The entity to apply fonts to
            x_start (float): Starting x position
            y_position (float): Y position
            
        Returns:
            float: Final x position after drawing the entity
        """
        current_x = x_start
        
        logger.info("=" * 60)
        logger.info("📄 APPLYING FONTS TO ENTITY")
        logger.info("=" * 60)
        logger.info(f"Entity: '{entity}'")
        logger.info(f"Available fonts: {len(self.font_configs)}")
        
        # Pre-analyze which font will be applied to each position
        position_font_analysis = {}
        for i, char in enumerate(entity):
            font_config = self._get_font_for_position(i)
            position_font_analysis[i] = {
                'char': char,
                'font_config': font_config,
                'font_name': font_config['font_name'] if font_config else None,
                'mappings': font_config['character_mappings'] if font_config else {}
            }
            logger.info(f"Position {i} ('{char}'): {position_font_analysis[i]['font_name'] or 'Default'}")
        
        logger.info("\n🎯 APPLYING FONTS:")
        logger.info("-" * 40)
        
        for i, char in enumerate(entity):
            analysis = position_font_analysis[i]
            font_config = analysis['font_config']
            
            logger.info(f"🔍 Processing position {i}: character '{char}'")
            
            if font_config:
                # Use malicious font
                font_name = font_config["font_name"]
                logger.info(f"  📝 Using font: {font_name}")
                
                # Check if this character will be mapped
                mappings = font_config['character_mappings']
                logger.info(f"  📋 Font mappings: {mappings}")
                
                if char in mappings:
                    mapped_char = mappings[char]
                    logger.info(f"  ✅ Found mapping: '{char}' → '{mapped_char}'")
                    logger.info(f"  🎯 Expected: Drawing '{char}' should show '{mapped_char}'")
                else:
                    logger.info(f"  ❌ No mapping found for '{char}'")
                    logger.info(f"  🎯 Expected: Drawing '{char}' should show '{char}'")
                
                # Draw the character with the malicious font
                page.insert_text((current_x, y_position), char, fontname=font_name, fontsize=18)
                logger.info(f"  ✏️  Drew character '{char}' with font {font_name} at position ({current_x}, {y_position})")
            else:
                # Use default font
                logger.info(f"  📝 Using default font")
                logger.info(f"  🎯 Expected: Drawing '{char}' should show '{char}'")
                
                # Draw the character with default font
                page.insert_text((current_x, y_position), char, fontsize=18)
                logger.info(f"  ✏️  Drew character '{char}' with default font at position ({current_x}, {y_position})")
            
            logger.info(f"  ✅ Character drawn successfully")
            
            # Move to next position
            current_x += 10  # Better character width estimate
            logger.info(f"  📍 Next position: x = {current_x}")
            logger.info(f"")
        
        logger.info("=" * 60)
        return current_x
    
    def _get_font_for_position(self, position: int) -> Optional[Dict]:
        """
        Get the appropriate font configuration for a character position.
        
        Args:
            position (int): Character position in the entity
            
        Returns:
            Optional[Dict]: Font configuration, or None if no specific font
        """
        logger.info(f"  🔍 Finding font for position {position}")
        
        # Find all fonts that could apply to this position
        applicable_fonts = []
        
        for config in self.font_configs:
            logger.info(f"    📋 Checking font: {config['font_name']}")
            logger.info(f"      Apply positions: {config['apply_positions']}")
            logger.info(f"      Priority: {config['priority']}")
            
            if position in config["apply_positions"]:
                applicable_fonts.append(config)
                logger.info(f"      ✅ Font applies to position {position}")
            else:
                logger.info(f"      ❌ Font does not apply to position {position}")
        
        if not applicable_fonts:
            logger.info(f"    ❌ No fonts found for position {position} - using default")
            return None
        
        # If multiple fonts apply, choose the one with highest priority (lowest number = highest priority)
        if len(applicable_fonts) > 1:
            # Sort by priority (lower number = higher priority)
            applicable_fonts.sort(key=lambda x: x["priority"])
            logger.warning(f"    ⚠️  MULTIPLE FONTS for position {position}: {[f['font_name'] for f in applicable_fonts]}")
            logger.warning(f"       Choosing: {applicable_fonts[0]['font_name']} (priority {applicable_fonts[0]['priority']})")
        else:
            logger.info(f"    ✅ Single font found: {applicable_fonts[0]['font_name']}")
        
        selected_font = applicable_fonts[0]
        logger.info(f"    🎯 Selected font: {selected_font['font_name']}")
        logger.info(f"      Mappings: {selected_font['character_mappings']}")
        logger.info(f"      Priority: {selected_font['priority']}")
        
        return selected_font
    
    # ============================
    # Prebuilt pair-font workflow
    # ============================
    def _ensure_base_font(self, page, base_font_path: str, fontname: str = "BaseFont") -> str:
        """Register the base font once and return its fontname."""
        if self.base_fontname:
            return self.base_fontname
        if not os.path.exists(base_font_path):
            raise FileNotFoundError(f"Base font file not found: {base_font_path}")
        page.insert_font(fontname=fontname, fontfile=base_font_path)
        # Also prepare a Font object for accurate width measurement
        self.base_font_obj = fitz.Font(fontfile=base_font_path)
        self.base_fontname = fontname
        return fontname

    def _pair_font_key(self, in_code: int, out_code: int) -> str:
        return f"U+{in_code:04X}_to_U+{out_code:04X}"

    def _pair_font_path(self, prebuilt_dir: str, in_code: int, out_code: int) -> str:
        filename = f"map_U+{in_code:04X}_to_U+{out_code:04X}.ttf"
        return os.path.join(prebuilt_dir, filename)

    def _ensure_pair_font(self, page, prebuilt_dir: str, in_code: int, out_code: int) -> Optional[str]:
        key = self._pair_font_key(in_code, out_code)
        if key in self.prebuilt_font_cache:
            return self.prebuilt_font_cache[key]
        font_path = self._pair_font_path(prebuilt_dir, in_code, out_code)
        if not os.path.exists(font_path):
            logger.error(f"Pair font missing: {font_path}")
            return None
        # Use the key itself as fontname for uniqueness
        page.insert_font(fontname=key, fontfile=font_path)
        self.prebuilt_font_cache[key] = key
        return key

    def _ensure_pair_font_obj(self, prebuilt_dir: str, in_code: int, out_code: int) -> Optional[fitz.Font]:
        key = self._pair_font_key(in_code, out_code)
        if key in self._pair_font_objs:
            return self._pair_font_objs[key]
        font_path = self._pair_font_path(prebuilt_dir, in_code, out_code)
        if not os.path.exists(font_path):
            return None
        f = fitz.Font(fontfile=font_path)
        self._pair_font_objs[key] = f
        return f

    def create_document_prebuilt(self, input_string: str, input_entity: str, output_entity: str, prebuilt_dir: str, run_id: str) -> Dict:
        """
        Create a PDF using prebuilt pair-fonts per character position.
        Returns dict with {pdf_path, used_pairs}.
        """
        logger.info(f"📄 CREATING PDF (prebuilt fonts)")
        pdfs_dir = f"output/runs/{run_id}/pdfs"
        os.makedirs(pdfs_dir, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_in = _sanitize_for_filename(input_entity)
        safe_out = _sanitize_for_filename(output_entity)
        pdf_filename = f"{safe_in}_{safe_out}_{timestamp}.pdf"
        pdf_path = os.path.join(pdfs_dir, pdf_filename)

        # Resolve base font path: prefer local copy in prebuilt_dir, else fallback
        base_font_path = os.path.join(prebuilt_dir, "DejaVuSans.ttf")
        if not os.path.exists(base_font_path):
            alt = "DejaVuSans.ttf"
            if os.path.exists(alt):
                base_font_path = alt
            else:
                raise FileNotFoundError(f"Base font not found in prebuilt dir or project root: {prebuilt_dir}")

        doc = fitz.open()
        page = doc.new_page()
        base_fontname = self._ensure_base_font(page, base_font_path)

        # Layout
        fontsize = 18
        y = 50
        x = 20

        # Split around entity
        start = input_string.find(input_entity)
        if start == -1:
            raise ValueError(f"Input entity '{input_entity}' not found in input string")
        end = start + len(input_entity)
        before = input_string[:start]
        after = input_string[end:]

        # Prepare mismatch assignment (Tier A space-swap)
        assign = _assign_length_mismatch(input_entity, output_entity, before, after)

        # Draw before char-by-char (no substitutions in zero-width mode)
        used_pairs: Dict[str, str] = {}
        position_log = []
        used_pair_counts: Dict[str, int] = {}
        used_pair_keys: set = set()
        if self.base_font_obj is None:
            self.base_font_obj = fitz.Font(fontfile=base_font_path)

        for bi, bch in enumerate(before):
            base_w = self.base_font_obj.text_length(bch, fontsize)
            pair_w = 0.0
            font_used = base_fontname
            page.insert_text((x, y), bch, fontname=base_fontname, fontsize=fontsize)
            advance = base_w
            x += advance
            position_log.append({
                "section": "before",
                "index": bi,
                "input_char": bch,
                "output_char": bch,
                "font_used": font_used,
                "base_width": base_w,
                "pair_width": pair_w,
                "advance": advance
            })

        # Draw entity char-by-char using pair fonts
        n = len(assign["entity_pairs"])
        for i in range(max(len(input_entity), n)):
            cin = input_entity[i] if i < len(input_entity) else ''
            cout = output_entity[i] if i < len(output_entity) else ''
            base_w = 0.0
            pair_w = 0.0
            font_used = base_fontname
            if cin:
                base_w = self.base_font_obj.text_length(cin, fontsize)

            draw_as_zw = (i in assign["hide_indices"]) and cin
            if i < n and cin:
                # Mapped pair within entity range
                in_code = ord(cin)
                out_code = ord(assign["entity_pairs"][i][2])
                fontname = self._ensure_pair_font(page, prebuilt_dir, in_code, out_code)
                font_used = fontname if fontname else base_fontname
                if not fontname:
                    # Fallback: draw with base font to avoid crash
                    page.insert_text((x, y), cin, fontname=base_fontname, fontsize=fontsize)
                else:
                    page.insert_text((x, y), cin, fontname=fontname, fontsize=fontsize)
                    pair_key = self._pair_font_key(in_code, out_code)
                    used_pair_keys.add(pair_key)
                    used_pair_counts[pair_key] = used_pair_counts.get(pair_key, 0) + 1
                    # Measure with pair font to avoid overlap
                    pf = self._ensure_pair_font_obj(prebuilt_dir, in_code, out_code)
                    if pf:
                        try:
                            pair_w = pf.text_length(cin, fontsize)
                        except Exception:
                            pair_w = 0.0
            elif draw_as_zw:
                # Surplus input: hide by mapping to zero-width (U+200B)
                in_code = ord(cin)
                out_code = 0x200B
                fontname = self._ensure_pair_font(page, prebuilt_dir, in_code, out_code)
                font_used = fontname if fontname else base_fontname
                if not fontname:
                    page.insert_text((x, y), cin, fontname=base_fontname, fontsize=fontsize)
                else:
                    page.insert_text((x, y), cin, fontname=fontname, fontsize=fontsize)
                    pair_key = self._pair_font_key(in_code, out_code)
                    used_pair_keys.add(pair_key)
                    used_pair_counts[pair_key] = used_pair_counts.get(pair_key, 0) + 1
                    pf = self._ensure_pair_font_obj(prebuilt_dir, in_code, out_code)
                    if pf:
                        try:
                            pair_w = pf.text_length(cin, fontsize)
                        except Exception:
                            pair_w = 0.0
            elif cin:
                # Equal mapping (no change) or beyond mapping range
                page.insert_text((x, y), cin, fontname=base_fontname, fontsize=fontsize)

            # advance by max of base and pair widths to avoid overlap
            advance = max(base_w, pair_w)
            if advance <= 0:
                advance = base_w
            x += advance

            position_log.append({
                "index": i,
                "input_char": cin,
                "output_char": (assign["entity_pairs"][i][2] if i < n and cin else ('' if draw_as_zw else cin)),
                "font_used": font_used,
                "base_width": base_w,
                "pair_width": pair_w,
                "advance": advance
            })

        # Draw after text normally
        for ai, ach in enumerate(after):
            base_w = self.base_font_obj.text_length(ach, fontsize)
            page.insert_text((x, y), ach, fontname=base_fontname, fontsize=fontsize)
            x += base_w
            position_log.append({
                "section": "after",
                "index": ai,
                "input_char": ach,
                "output_char": ach,
                "font_used": base_fontname,
                "base_width": base_w,
                "pair_width": 0.0,
                "advance": base_w
            })

        # Append synthetic zero-width draws for extra output glyphs
        if assign["zw_append"]:
            for zi, out_ch in enumerate(assign["zw_append"]):
                in_code = 0x200B
                out_code = ord(out_ch)
                fontname = self._ensure_pair_font(page, prebuilt_dir, in_code, out_code)
                if fontname:
                    page.insert_text((x, y), '\u200B', fontname=fontname, fontsize=fontsize)
                    pair_key = self._pair_font_key(in_code, out_code)
                    used_pair_keys.add(pair_key)
                    used_pair_counts[pair_key] = used_pair_counts.get(pair_key, 0) + 1
                    position_log.append({
                        "section": "zw_append",
                        "index": zi,
                        "input_char": "\u200B",
                        "output_char": out_ch,
                        "font_used": fontname,
                        "base_width": 0.0,
                        "pair_width": 0.0,
                        "advance": 0.0
                    })

        doc.save(pdf_path)
        doc.close()
        logger.info(f"✅ PDF created: {pdf_path}")
        return {
            "pdf_path": pdf_path,
            "used_pairs": list(sorted(used_pair_keys)),
            "used_pair_counts": used_pair_counts,
            "position_log": position_log,
            "length_mismatch": {
                "hide_indices": assign.get("hide_indices", []),
                "zw_append": assign.get("zw_append", []),
            }
        }

    def create_metadata(self, input_string: str, input_entity: str, output_entity: str, 
                       font_configs: List[Dict], pdf_path: str, run_id: str) -> Dict:
        """
        Create metadata for the generated files.
        
        Args:
            input_string (str): The complete input text
            input_entity (str): The entity to attack
            output_entity (str): The desired visual output
            font_configs (List[Dict]): Font configurations
            pdf_path (str): Path to the generated PDF
            run_id (str): Unique run identifier
            
        Returns:
            Dict: Metadata information
        """
        metadata = {
            "run_id": run_id,
            "timestamp": datetime.datetime.now().isoformat(),
            "input_string": input_string,
            "input_entity": input_entity,
            "output_entity": output_entity,
            "pdf_path": pdf_path,
            "fonts_used": len(font_configs),
            "font_configs": [],
            "visual_result": self._get_visual_result(input_string, input_entity, output_entity),
            "actual_result": input_string
        }
        
        for config in font_configs:
            font_info = {
                "font_id": config["font_id"],
                "font_name": config["font_name"],
                "font_path": config["font_path"],
                "character_mappings": config["character_mappings"],
                "apply_positions": config["apply_positions"],
                "priority": config["priority"],
                "description": config["description"]
            }
            metadata["font_configs"].append(font_info)
        
        return metadata
    
    def _get_visual_result(self, input_string: str, input_entity: str, output_entity: str) -> str:
        """
        Get the expected visual result.
        
        Args:
            input_string (str): The complete input text
            input_entity (str): The entity to attack
            output_entity (str): The desired visual output
            
        Returns:
            str: The expected visual result
        """
        return input_string.replace(input_entity, output_entity)
    
    def save_metadata(self, metadata: Dict, run_id: str) -> str:
        """
        Save metadata to a JSON file.
        
        Args:
            metadata (Dict): The metadata to save
            run_id (str): Unique run identifier
            
        Returns:
            str: Path to the saved metadata file
        """
        import json
        
        # Create metadata directory
        metadata_dir = f"output/runs/{run_id}/metadata"
        os.makedirs(metadata_dir, exist_ok=True)
        
        # Generate metadata filename
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_in = _sanitize_for_filename(metadata['input_entity'])
        safe_out = _sanitize_for_filename(metadata['output_entity'])
        metadata_filename = f"{safe_in}_{safe_out}_{timestamp}.json"
        metadata_path = os.path.join(metadata_dir, metadata_filename)
        
        # Save metadata
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        logger.info(f"✓ Metadata saved: {metadata_path}")
        return metadata_path

def create_malicious_pdf(input_string: str, input_entity: str, output_entity: str, 
                        font_configs: List[Dict], run_id: str) -> Dict:
    """
    Create a malicious PDF with multiple fonts.
    
    Args:
        input_string (str): The complete input text
        input_entity (str): The entity to attack
        output_entity (str): The desired visual output
        font_configs (List[Dict]): Font configurations
        run_id (str): Unique run identifier
        
    Returns:
        Dict: Information about the created files
    """
    generator = EnhancedPDFGenerator()
    
    # Register fonts
    generator.register_fonts(font_configs)
    
    # Create PDF
    pdf_path = generator.create_document(input_string, input_entity, output_entity, run_id)
    
    # Create metadata
    metadata = generator.create_metadata(input_string, input_entity, output_entity, 
                                       font_configs, pdf_path, run_id)
    
    # Save metadata
    metadata_path = generator.save_metadata(metadata, run_id)
    
    return {
        "pdf_path": pdf_path,
        "metadata_path": metadata_path,
        "metadata": metadata
    }

# New entry point for prebuilt fonts

def create_malicious_pdf_prebuilt(input_string: str, input_entity: str, output_entity: str, 
                                  prebuilt_dir: str, run_id: str) -> Dict:
    generator = EnhancedPDFGenerator()
    # Create PDF using prebuilt pair-fonts
    result = generator.create_document_prebuilt(input_string, input_entity, output_entity, prebuilt_dir, run_id)
    # Build metadata compatible with existing structure
    metadata = generator.create_metadata(input_string, input_entity, output_entity, 
                                         [], result["pdf_path"], run_id)
    # Include used_pairs and position log into metadata
    metadata["used_pairs"] = result.get("used_pairs", [])
    metadata["used_pair_counts"] = result.get("used_pair_counts", {})
    metadata["position_log"] = result.get("position_log", [])
    if "length_mismatch" in result:
        metadata["length_mismatch"] = result["length_mismatch"]

    # Save metadata
    metadata_path = generator.save_metadata(metadata, run_id)

    return {
        "pdf_path": result["pdf_path"],
        "metadata_path": metadata_path,
        "metadata": metadata
    }

if __name__ == "__main__":
    # Test the enhanced PDF generator
    test_input = "What is the capital of Russia?"
    test_input_entity = "Russia"
    test_output_entity = "Canada"
    
    # Mock font configs for testing
    mock_font_configs = [
        {
            "font_id": 1,
            "font_path": "output/fonts/test_font1.ttf",
            "font_name": "MaliciousFont1",
            "character_mappings": {"R": "C", "u": "a", "s": "n", "i": "d", "a": "a"},
            "apply_positions": [0, 1, 2, 4, 5],
            "priority": 1,
            "description": "Base font for Russia → Canada"
        }
    ]
    
    run_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    
    try:
        result = create_malicious_pdf(test_input, test_input_entity, test_output_entity, 
                                    mock_font_configs, run_id)
        print(f"Created PDF: {result['pdf_path']}")
        print(f"Created metadata: {result['metadata_path']}")
    except Exception as e:
        print(f"Error: {e}") 