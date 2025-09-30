#!/usr/bin/env python3
"""Debug with a real run ID that has actual mapping context."""

from app import create_app
app = create_app()

with app.app_context():
    from app.services.pipeline.enhancement_methods.content_stream_renderer import ContentStreamRenderer
    from pathlib import Path

    print("Testing with REAL run_id: 32edc5f7-29c3-4782-b1e6-b91461b1d4c1")

    # Use simple mapping but with REAL run_id
    simple_mapping = {"the": "not"}

    renderer = ContentStreamRenderer()
    original_pdf = Path('data/pipeline_runs/32edc5f7-29c3-4782-b1e6-b91461b1d4c1/Quiz6.pdf')
    output_pdf = Path('/tmp/debug_real_run.pdf')

    print(f"Input: {original_pdf}")
    print(f"Mapping: {simple_mapping}")

    # Use the REAL run_id so mapping_context gets loaded
    result = renderer.render(
        run_id='32edc5f7-29c3-4782-b1e6-b91461b1d4c1',  # THIS IS THE KEY!
        original_pdf=original_pdf,
        destination=output_pdf,
        mapping=simple_mapping
    )

    print(f"Result replacements: {result.get('replacements', 0)}")
    print(f"Result matches_found: {result.get('matches_found', 0)}")

    if result.get('replacements', 0) == 0:
        print("❌ Still no replacements found")
    else:
        print("✅ Replacements found!")