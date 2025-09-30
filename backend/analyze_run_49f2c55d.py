#!/usr/bin/env python3
"""
Comprehensive analysis of run 49f2c55d to understand suffix formatting and drift issues.
"""

import sys
import json
import sqlite3
from pathlib import Path
import io

# Set up Flask app context
from app import create_app
app = create_app()

def analyze_tj_reconstruction():
    """Analyze the TJ reconstruction process step by step."""
    with app.app_context():
        from app.services.pipeline.enhancement_methods.base_renderer import BaseRenderer
        from PyPDF2 import PdfReader
        from PyPDF2.generic import ContentStream
        import fitz

        # Get the question manipulations from the database for run 49f2c55d
        conn = sqlite3.connect('data/fairtestai.db')
        cursor = conn.cursor()

        cursor.execute('''
            SELECT qm.question_number, qm.substring_mappings, qm.original_text
            FROM question_manipulations qm
            WHERE qm.pipeline_run_id = '49f2c55d-ab59-471b-930c-eea3b5ca228c'
            ORDER BY qm.question_number
        ''')

        mappings = {}
        for row in cursor.fetchall():
            q_num, mappings_json, original_text = row
            if mappings_json:
                question_mappings = json.loads(mappings_json)
                for mapping in question_mappings:
                    original = mapping.get('original')
                    replacement = mapping.get('replacement')
                    if original and replacement:
                        mappings[original] = replacement

        conn.close()

        print(f'Found {len(mappings)} text mappings:')
        for orig, repl in mappings.items():
            print(f'  "{orig}" -> "{repl}"')

        # Analyze the original PDF structure
        original_pdf = Path('data/pipeline_runs/49f2c55d-ab59-471b-930c-eea3b5ca228c/Quiz6.pdf')
        pdf_bytes = original_pdf.read_bytes()
        reader = PdfReader(io.BytesIO(pdf_bytes))
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        page = reader.pages[0]
        content_stream = ContentStream(page.get_contents(), reader)

        # Extract and analyze text segments
        base_renderer = BaseRenderer()
        segments, tokens, tj_hits = base_renderer._extract_text_segments(content_stream, page)

        print(f"\n=== PDF STRUCTURE ANALYSIS ===")
        print(f"Found {len(segments)} text segments, {tokens} tokens, {tj_hits} TJ hits")

        # Analyze each segment for font context
        print(f"\n=== DETAILED SEGMENT ANALYSIS ===")
        for i, segment in enumerate(segments):
            text = segment.get('text', '')
            operators = segment.get('operators', [])

            # Look for mappings in this segment
            has_mappings = any(original in text for original in mappings.keys())

            if has_mappings:
                print(f"\nSegment {i} (HAS MAPPINGS): '{text[:100]}...'")
                print(f"  Full text: '{text}'")

                # Extract font context from operators
                current_font = None
                current_fontsize = None

                for op_data in operators:
                    operands = op_data.get('operands', [])
                    operator = op_data.get('operator', b'')

                    if operator == b'Tf' and len(operands) >= 2:
                        current_font = str(operands[0])
                        current_fontsize = float(operands[1])
                        print(f"    Font context: {current_font} {current_fontsize}pt")
                    elif operator in [b'TJ', b'Tj']:
                        print(f"    Text operator: {operator} with operands: {operands}")

                        # Analyze the TJ array structure
                        if operator == b'TJ' and operands:
                            tj_array = operands[0]
                            if hasattr(tj_array, '__iter__'):
                                for j, element in enumerate(tj_array):
                                    if hasattr(element, '__str__'):
                                        element_text = str(element)
                                        if any(orig in element_text for orig in mappings.keys()):
                                            print(f"      TJ[{j}]: '{element_text}' (CONTAINS MAPPING)")
                                        else:
                                            print(f"      TJ[{j}]: '{element_text}'")
                                    else:
                                        print(f"      TJ[{j}]: {element} (numeric)")

                # Simulate our replacement process
                print(f"  Simulating replacement...")
                for original, replacement in mappings.items():
                    if original in text:
                        print(f"    Found '{original}' -> '{replacement}'")
                        # Calculate what our current algorithm would do
                        target_width = len(original) * 6.0  # Estimate
                        courier_size = target_width / (len(replacement) * 0.6)
                        print(f"    Current algorithm: Courier {courier_size:.2f}pt")
                        print(f"    Current font context: {current_font} {current_fontsize}pt")

                        # Show the split that would happen
                        start_pos = text.find(original)
                        prefix = text[:start_pos]
                        suffix = text[start_pos + len(original):]
                        print(f"    Split: prefix='{prefix}' | replacement='{replacement}' | suffix='{suffix}'")

        doc.close()

        # Now analyze the reconstructed output
        print(f"\n=== RECONSTRUCTED OUTPUT ANALYSIS ===")

        # Read the debug data
        debug_file = Path('data/pipeline_runs/49f2c55d-ab59-471b-930c-eea3b5ca228c/artifacts/stream_rewrite-overlay/debug.pdf/after_reconstruction.json')
        if debug_file.exists():
            with open(debug_file) as f:
                debug_data = json.load(f)

            print("Reconstructed operations:")
            for i, op in enumerate(debug_data.get('operations', [])):
                operator = op.get('operator')
                operands = op.get('operands', [])
                print(f"  {i}: {operator} {operands}")

        # Analyze the final output PDF
        output_pdf = Path('data/pipeline_runs/49f2c55d-ab59-471b-930c-eea3b5ca228c/artifacts/stream_rewrite-overlay/after_stream_rewrite.pdf')
        if output_pdf.exists():
            print(f"\n=== OUTPUT PDF ANALYSIS ===")
            output_doc = fitz.open(str(output_pdf))
            output_page = output_doc[0]
            text_dict = output_page.get_text('dict')

            # Find text with replacement content
            for block_num, block in enumerate(text_dict['blocks']):
                if 'lines' in block:
                    for line_num, line in enumerate(block['lines']):
                        for span_num, span in enumerate(line['spans']):
                            span_text = span.get('text', '')
                            font = span.get('font', '')
                            size = span.get('size', 0)

                            # Check if this span contains our replacements
                            if any(repl in span_text for repl in mappings.values()):
                                print(f"  Replacement found: '{span_text}' (font: {font}, size: {size:.2f})")

                            # Check for Courier font usage
                            if 'Courier' in font:
                                print(f"  Courier span: '{span_text}' (size: {size:.2f})")

            output_doc.close()

if __name__ == "__main__":
    analyze_tj_reconstruction()