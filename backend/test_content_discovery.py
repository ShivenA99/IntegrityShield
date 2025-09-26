#!/usr/bin/env python3

from app import create_app
from app.services.pipeline.content_discovery_service import ContentDiscoveryService
import asyncio

async def test_content_discovery():
    app = create_app()

    with app.app_context():
        service = ContentDiscoveryService()
        run_id = '0a9201ff-6949-43ff-a93b-f5a6eefa3867'

        try:
            result = await service.run(run_id, {})
            print(f'Questions detected: {result}')

            # Load the updated structured data
            structured = service.structured_manager.load(run_id)
            questions = structured.get('questions', [])

            print(f'\nFound {len(questions)} questions:')
            for i, q in enumerate(questions):
                print(f'  Q{i+1}: {q.get("question_id")} - {q.get("q_number")}')
                print(f'       Stem: {q.get("stem_text", "")[:100]}...')
                print(f'       Options: {list(q.get("options", {}).keys())}')
                print(f'       Overlay targets: {len(q.get("image_overlay_targets", []))}')

                for target in q.get('image_overlay_targets', [])[:2]:  # Show first 2 targets
                    print(f'         - {target.get("semantic_role")}: {target.get("target_text")} -> {target.get("replacement_text")}')
                print()

        except Exception as e:
            print(f'Error: {e}')
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_content_discovery())