#!/usr/bin/env python3
"""Simple debug script to find why no replacements are found."""

from app import create_app
app = create_app()

with app.app_context():
    from app.services.pipeline.enhancement_methods.content_stream_renderer import ContentStreamRenderer
    from pathlib import Path

    print("Testing simple mapping...")

    # Use VERY simple mapping for testing
    simple_mapping = {"the": "not"}

    renderer = ContentStreamRenderer()
    original_pdf = Path('data/pipeline_runs/32edc5f7-29c3-4782-b1e6-b91461b1d4c1/Quiz6.pdf')
    output_pdf = Path('/tmp/debug_simple.pdf')

    print(f"Input: {original_pdf}")
    print(f"Mapping: {simple_mapping}")

    result = renderer.render(
        run_id='debug_simple',
        original_pdf=original_pdf,
        destination=output_pdf,
        mapping=simple_mapping
    )

    print(f"Result replacements: {result.get('replacements', 0)}")
    print(f"Result matches_found: {result.get('matches_found', 0)}")

    if result.get('replacements', 0) == 0:
        print("❌ NO REPLACEMENTS FOUND - This is the core issue!")
    else:
        print("✅ Replacements found!")