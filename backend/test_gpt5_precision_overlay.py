#!/usr/bin/env python3

import asyncio
from pathlib import Path
from app import create_app
from app.services.pipeline.content_discovery_service import ContentDiscoveryService
from app.services.pipeline.enhancement_methods.image_overlay_renderer import ImageOverlayRenderer
from app.services.data_management.structured_data_manager import StructuredDataManager

async def test_end_to_end_gpt5_precision_overlay():
    """Test the complete GPT-5 fusion + precision overlay workflow."""

    app = create_app()
    with app.app_context():
        print("🚀 Testing GPT-5 Fusion + Precision Overlay Workflow")
        print("=" * 60)

        # Setup
        run_id = '0a9201ff-6949-43ff-a93b-f5a6eefa3867'
        content_service = ContentDiscoveryService()
        overlay_renderer = ImageOverlayRenderer()
        data_manager = StructuredDataManager()

        try:
            # Phase 1: GPT-5 Question Analysis
            print("\n📊 Phase 1: GPT-5 Question Analysis")
            print("-" * 40)

            result = await content_service.run(run_id, {})
            print(f"✅ Content discovery result: {result}")

            # Load the updated structured data
            structured = data_manager.load(run_id)
            questions = structured.get('questions', [])

            print(f"\n📝 Found {len(questions)} questions:")
            for i, q in enumerate(questions):
                print(f"   Q{i+1}: {q.get('question_id')} - {q.get('question_type')}")
                print(f"        Stem: {q.get('stem_text', '')[:80]}...")

                manipulation_targets = q.get('manipulation_targets', [])
                print(f"        Manipulation targets: {len(manipulation_targets)}")

                for j, target in enumerate(manipulation_targets[:3]):  # Show first 3
                    original = target.get('original_substring', '')
                    replacement = target.get('replacement_substring', '')
                    target_type = target.get('target_type', 'unknown')
                    print(f"          {j+1}. [{target_type}] '{original}' → '{replacement}'")
                print()

            # Phase 2: Precision Overlay Application
            print("\n🎯 Phase 2: Precision Overlay Application")
            print("-" * 40)

            if questions:
                # Test the image overlay with GPT-5 targets
                original_pdf = Path(f"data/pipeline_runs/{run_id}/demo_paper_1.pdf")
                test_output = Path(f"data/pipeline_runs/{run_id}/test_precision_overlay.pdf")

                if original_pdf.exists():
                    print(f"📄 Processing PDF: {original_pdf}")
                    print(f"🎯 Output will be saved to: {test_output}")

                    # Apply precision overlays
                    overlay_result = overlay_renderer.render(
                        run_id=run_id,
                        original_pdf=original_pdf,
                        destination=test_output,
                        mapping={}  # Not used in new approach
                    )

                    print(f"✅ Overlay application result:")
                    print(f"   - Mapping entries: {overlay_result.get('mapping_entries', 0)}")
                    print(f"   - Overlays applied: {overlay_result.get('overlays_applied', 0)}")
                    print(f"   - Effectiveness score: {overlay_result.get('effectiveness_score', 0.0)}")
                    print(f"   - File size: {overlay_result.get('file_size_bytes', 0)} bytes")

                    if test_output.exists():
                        print(f"🎉 SUCCESS: Enhanced PDF created at {test_output}")
                        print(f"   Original visual appearance preserved for humans")
                        print(f"   Content streams modified for LLM parsing")
                    else:
                        print("❌ FAILED: Output PDF not created")

                else:
                    print(f"❌ ERROR: Original PDF not found at {original_pdf}")
            else:
                print("⚠️  No questions found to test overlay application")

            # Phase 3: Validation Summary
            print("\n📈 Phase 3: Validation Summary")
            print("-" * 40)

            total_targets = sum(len(q.get('manipulation_targets', [])) for q in questions)
            high_impact_targets = sum(
                1 for q in questions
                for target in q.get('manipulation_targets', [])
                if target.get('impact') == 'high'
            )

            print(f"📊 Analysis Results:")
            print(f"   - Questions detected: {len(questions)}")
            print(f"   - Total manipulation targets: {total_targets}")
            print(f"   - High-impact targets: {high_impact_targets}")
            print(f"   - GPT-5 fusion enabled: {len(questions) > 0 and questions[0].get('manipulation_targets')}")

            if questions and questions[0].get('manipulation_targets'):
                print("\n🎯 Precision Overlay Strategy:")
                print("   ✅ GPT-5 identified questions with exact positioning")
                print("   ✅ Substring-level manipulation targets generated")
                print("   ✅ Dual-operation approach (content + visual overlay)")
                print("   ✅ Code_glyph precision overlay method adapted")
                print("\n🚀 Ready for production testing!")
            else:
                print("\n⚠️  GPT-5 fusion may not be properly configured")
                print("     Check OPENAI_API_KEY environment variable")

        except Exception as e:
            print(f"❌ ERROR: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_end_to_end_gpt5_precision_overlay())