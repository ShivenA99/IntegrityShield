"""Format validation test for StreamlinedMappingService - checks prompt structure and API format."""

import json
import os
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from app.services.mapping.streamlined_mapping_service import (
    StreamlinedMappingService,
    MAPPING_GENERATION_SCHEMA,
)


def test_mapping_schema():
    """Test that MAPPING_GENERATION_SCHEMA is correctly defined."""
    print("Testing MAPPING_GENERATION_SCHEMA...")
    
    assert "name" in MAPPING_GENERATION_SCHEMA
    assert "schema" in MAPPING_GENERATION_SCHEMA
    assert MAPPING_GENERATION_SCHEMA["name"] == "mappingBatch"
    
    schema = MAPPING_GENERATION_SCHEMA["schema"]
    assert schema["type"] == "object"
    assert "properties" in schema
    assert "mappings" in schema["properties"]
    
    mappings_prop = schema["properties"]["mappings"]
    assert mappings_prop["type"] == "array"
    assert "items" in mappings_prop
    
    item_schema = mappings_prop["items"]
    assert "properties" in item_schema
    assert "original" in item_schema["properties"]
    assert "replacement" in item_schema["properties"]
    
    print("✓ MAPPING_GENERATION_SCHEMA is correctly defined")


def test_prompt_structure():
    """Test that prompt building includes JSON schema and failure rationales."""
    print("\nTesting prompt structure...")
    
    service = StreamlinedMappingService()
    
    question_data = {
        "question_type": "mcq_single",
        "stem_text": "What is the unit of electrical resistance?",
        "gold_answer": "B",
        "options": {
            "A": "Ampere",
            "B": "Ohm",
            "C": "Coulomb",
            "D": "Volt"
        },
    }
    
    target_config = {
        "target_option": "C",
        "target_option_text": "Coulomb",
        "signal_strategy": None,
    }
    
    # Test prompt without failure rationales
    prompt = service._build_generation_prompt(
        question_data=question_data,
        target_config=target_config,
        failure_rationales=None,
    )
    
    assert "QUESTION TYPE" in prompt
    assert "QUESTION TEXT" in prompt
    assert "GOLD ANSWER" in prompt
    assert "OPTIONS" in prompt
    assert "TARGET" in prompt
    assert "OUTPUT FORMAT" in prompt
    assert "JSON" in prompt
    assert "mappings" in prompt.lower()
    
    print("✓ Prompt structure is correct (without failure rationales)")
    
    # Test prompt with failure rationales
    failure_rationales = [
        "Set 1, Mapping 1: Mapping did not change the answer",
        "Set 2, Mapping 1: Target option not matched",
    ]
    
    prompt_with_rationales = service._build_generation_prompt(
        question_data=question_data,
        target_config=target_config,
        failure_rationales=failure_rationales,
    )
    
    assert "PREVIOUS ATTEMPTS FAILED" in prompt_with_rationales
    for rationale in failure_rationales:
        assert rationale in prompt_with_rationales
    
    print("✓ Prompt structure is correct (with failure rationales)")


def test_target_config_determination():
    """Test that target configs are correctly determined for different question types."""
    print("\nTesting target config determination...")
    
    service = StreamlinedMappingService()
    
    # Test MCQ
    mcq_data = {
        "question_type": "mcq_single",
        "gold_answer": "B",
        "options": {
            "A": "Option A",
            "B": "Option B",
            "C": "Option C",
            "D": "Option D",
        },
    }
    
    mcq_configs = service._determine_target_configs(mcq_data, "mcq_single")
    assert len(mcq_configs) == 3
    assert all(c.get("target_option") is not None for c in mcq_configs[:3])
    assert all(c.get("signal_strategy") is None for c in mcq_configs)
    
    print(f"✓ MCQ configs: {len(mcq_configs)} sets, targeting options: {[c.get('target_option') for c in mcq_configs]}")
    
    # Test signal-based question
    signal_data = {
        "question_type": "short_answer",
        "gold_answer": "Some answer",
    }
    
    signal_configs = service._determine_target_configs(signal_data, "short_answer")
    assert len(signal_configs) == 3
    assert all(c.get("target_option") is None for c in signal_configs)
    assert all(c.get("signal_strategy") is not None for c in signal_configs)
    
    print(f"✓ Signal configs: {len(signal_configs)} sets, strategies: {[c.get('signal_strategy') for c in signal_configs]}")

    # Test true/false without explicit options
    tf_data = {"question_type": "true_false", "gold_answer": "True"}
    tf_configs = service._determine_target_configs(tf_data, "true_false")
    assert len(tf_configs) == 3
    assert tf_configs[0]["target_option"] == "False"
    print(f"✓ True/False configs: {[c.get('target_option') for c in tf_configs]}")


def test_label_extraction():
    """Test label extraction from various formats."""
    print("\nTesting label extraction...")
    
    service = StreamlinedMappingService()
    
    test_cases = [
        ("B", "B"),
        ("B.", "B"),
        ("B)", "B"),
        ("B. Temperature", "B"),
        ("B) Temperature", "B"),
        ("B Temperature", "B"),
        ("A", "A"),
    ]
    
    for input_text, expected in test_cases:
        result = service._extract_label_from_string(input_text)
        assert result == expected, f"Expected {expected} for '{input_text}', got {result}"
    
    print("✓ Label extraction works correctly")


def test_status_structure():
    """Test that status dataclasses are correctly structured."""
    print("\nTesting status structure...")
    
    from app.services.mapping.streamlined_mapping_service import (
        QuestionGenerationStatus,
        MappingSetStatus,
        ValidationOutcome,
    )
    
    # Test MappingSetStatus
    set_status = MappingSetStatus(
        attempt=1,
        set_index=1,
        target_option="C",
        mappings_count=2,
    )
    assert set_status.attempt == 1
    assert set_status.set_index == 1
    assert set_status.target_option == "C"
    
    # Test ValidationOutcome
    outcome = ValidationOutcome(
        attempt=1,
        set_index=1,
        mapping_index=0,
        is_valid=True,
        confidence=0.9,
        deviation_score=0.8,
        reasoning="Valid mapping",
        test_answer="C",
    )
    assert outcome.is_valid is True
    assert outcome.confidence == 0.9
    
    # Test QuestionGenerationStatus
    status = QuestionGenerationStatus(
        question_id=1,
        question_number="1",
        status="generating",
    )
    assert status.question_id == 1
    assert status.status == "generating"
    assert len(status.mapping_sets_generated) == 0
    assert len(status.validation_outcomes) == 0
    
    print("✓ Status structures are correctly defined")


def main():
    """Run all format validation tests."""
    print("=" * 60)
    print("Streamlined Mapping Service - Format Validation Tests")
    print("=" * 60)
    
    try:
        test_mapping_schema()
        test_prompt_structure()
        test_target_config_determination()
        test_label_extraction()
        test_status_structure()
        
        print("\n" + "=" * 60)
        print("✓ All format validation tests passed!")
        print("=" * 60)
        return 0
        
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())









