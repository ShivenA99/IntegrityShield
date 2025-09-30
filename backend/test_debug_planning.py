#!/usr/bin/env python3
"""
Test script to debug our Courier font TJ replacement strategy.
"""

import sys
import json
import sqlite3
from pathlib import Path

# Set up Flask app context
from app import create_app
app = create_app()

def test_courier_replacement():
    """Test our updated TJ replacement logic."""
    with app.app_context():
        from app.services.pipeline.enhancement_methods.content_stream_renderer import ContentStreamRenderer

        # Get the question manipulations from the database for run 32edc5f7
        conn = sqlite3.connect('data/fairtestai.db')
        cursor = conn.cursor()

        cursor.execute('''
            SELECT qm.question_number, qm.substring_mappings, qm.original_text
            FROM question_manipulations qm
            WHERE qm.pipeline_run_id = '32edc5f7-29c3-4782-b1e6-b91461b1d4c1'
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

        if mappings:
            # Test our content stream renderer
            renderer = ContentStreamRenderer()

            original_pdf = Path('data/pipeline_runs/32edc5f7-29c3-4782-b1e6-b91461b1d4c1/Quiz6.pdf')
            output_pdf = Path('/tmp/test_courier_debug.pdf')

            print(f'\nTesting content stream renderer...')
            print(f'Input: {original_pdf}')
            print(f'Output: {output_pdf}')

            try:
                # DEBUG: Let's manually test the planning phase first
try:
    from app.services.pipeline.enhancement_methods.base_renderer import BaseRenderer
    base_renderer = BaseRenderer()
    
    import fitz
    import io
    from PyPDF2 import PdfReader
    from PyPDF2.generic import ContentStream
    
    # Read the PDF and analyze segments
    pdf_bytes = original_pdf.read_bytes()
    reader = PdfReader(io.BytesIO(pdf_bytes))
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    
    page = reader.pages[0]
    content_stream = ContentStream(page.get_contents(), reader)
    
    # Extract text segments
    segments, tokens, tj_hits = base_renderer._extract_text_segments(content_stream, page)
    print(f"Found {len(segments)} text segments, {tokens} tokens, {tj_hits} TJ hits")
    
    for i, segment in enumerate(segments[:3]):
        print(f"Segment {i}: {segment.get('text', '')[:50]}...")
    
    # Try to build mapping context
    mapping_context = {}
    for original, replacement in mappings.items():
        # Create fake context for testing
        mapping_context[original] = [{
            'original': original,
            'replacement': replacement,
            'page': 0,
            'start_pos': 0,
            'end_pos': len(original)
        }]
    
    print(f"
Testing replacement planning with {len(mapping_context)} mappings...")
    
    replacements = base_renderer._plan_replacements(
        segments, 
        list(mapping_context.values())[0] if mapping_context else [],  # Just pass first context
        set(),
        'debug_test',
        0,
        doc[0]
    )
    
    print(f"_plan_replacements returned {len(replacements)} replacements")
    for repl in replacements:
        print(f"  - {repl}")
    
    doc.close()
    
except Exception as e:
    import traceback
    print(f"Debug failed: {e}")
    traceback.print_exc()

result = renderer.render(
                    run_id='test_courier_debug',
                    original_pdf=original_pdf,
                    destination=output_pdf,
                    mapping=mappings
                )

                print(f'✓ Rendering completed successfully!')
                print(f'Result: {result}')

                # Check if output file was created
                if output_pdf.exists():
                    print(f'✓ Output PDF created: {output_pdf.stat().st_size} bytes')

                    # Quick analysis of the output
                    import fitz
                    doc = fitz.open(str(output_pdf))
                    page = doc[0]
                    text_dict = page.get_text('dict')

                    print(f'\nQuick analysis of output PDF:')
                    for block_num, block in enumerate(text_dict['blocks'][:5]):
                        if 'lines' in block:
                            for line_num, line in enumerate(block['lines'][:3]):
                                for span in line['spans'][:2]:
                                    text = span.get('text', '')[:50]
                                    if any(repl in text for repl in mappings.values()):
                                        print(f'  Found replacement: "{text}"')

                    doc.close()
                else:
                    print('✗ Output PDF not created')

            except Exception as e:
                import traceback
                print(f'✗ Rendering failed: {e}')
                traceback.print_exc()
        else:
            print('No mappings found to test with')

if __name__ == "__main__":
    test_courier_replacement()