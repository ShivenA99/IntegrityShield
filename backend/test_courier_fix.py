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