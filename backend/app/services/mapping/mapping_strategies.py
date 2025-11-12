"""Strategy system for mapping generation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .prompt_templates import (
    MCQ_REPLACEMENT_PROMPT,
    TRUE_FALSE_REPLACEMENT_PROMPT,
    LONG_FORM_REPLACEMENT_PROMPT,
)


@dataclass
class MappingStrategy:
    """Strategy definition for mapping generation."""
    name: str
    question_types: List[str]
    reasoning_steps: List[str]
    prompt_template: str
    validation_criteria: Dict[str, Any]


# Default Strategy: "replacement"
MCQ_REPLACEMENT_STRATEGY = MappingStrategy(
    name="replacement",
    question_types=["mcq_single", "mcq_multi"],
    reasoning_steps=[
        "Identify key terms in question stem that affect answer",
        "Find replacement that changes answer to target wrong option",
        "Ensure replacement is semantically meaningful",
        "Verify replacement causes answer deviation"
    ],
    prompt_template=MCQ_REPLACEMENT_PROMPT,
    validation_criteria={
        "target_wrong_answer_required": True,
        "answer_deviation_required": True
    }
)

TRUE_FALSE_REPLACEMENT_STRATEGY = MappingStrategy(
    name="replacement",
    question_types=["true_false"],
    reasoning_steps=[
        "Identify terms that determine True/False",
        "Replace to flip the answer",
        "Ensure replacement is natural"
    ],
    prompt_template=TRUE_FALSE_REPLACEMENT_PROMPT,
    validation_criteria={
        "answer_flip_required": True
    }
)

LONG_FORM_REPLACEMENT_STRATEGY = MappingStrategy(
    name="replacement",
    question_types=["long_answer", "essay", "short_answer"],
    reasoning_steps=[
        "Identify key concepts in question",
        "Replace to change question focus",
        "Ensure deviation is verifiable",
        "Verify replacement affects answer meaningfully"
    ],
    prompt_template=LONG_FORM_REPLACEMENT_PROMPT,
    validation_criteria={
        "verifiable_deviation_required": True
    }
)


class StrategyRegistry:
    """Registry for mapping strategies."""
    
    def __init__(self):
        self.strategies: Dict[str, MappingStrategy] = {}
        self._register_default_strategies()
    
    def _register_default_strategies(self):
        """Register default strategies."""
        self.register_strategy(MCQ_REPLACEMENT_STRATEGY)
        self.register_strategy(TRUE_FALSE_REPLACEMENT_STRATEGY)
        self.register_strategy(LONG_FORM_REPLACEMENT_STRATEGY)
    
    def register_strategy(self, strategy: MappingStrategy):
        """Register a strategy."""
        for question_type in strategy.question_types:
            key = f"{strategy.name}:{question_type}"
            self.strategies[key] = strategy
    
    def get_strategy(
        self, 
        question_type: str, 
        strategy_name: str = "replacement"
    ) -> Optional[MappingStrategy]:
        """Get strategy for question type and strategy name."""
        key = f"{strategy_name}:{question_type}"
        return self.strategies.get(key)
    
    def _format_options(self, options: Dict[str, Any] | None) -> str:
        """Convert options dictionary to formatted string for prompt template."""
        if not options:
            return "None"
        
        if not isinstance(options, dict):
            return str(options)
        
        # Format as "Key: Value" pairs, ensuring all keys are strings
        formatted_pairs = []
        for key, value in options.items():
            # Convert key to string to handle any non-string keys
            key_str = str(key)
            value_str = str(value) if value is not None else ""
            formatted_pairs.append(f"{key_str}: {value_str}")
        
        return ", ".join(formatted_pairs)
    
    def build_prompt(
        self, 
        strategy: MappingStrategy, 
        question_data: Dict[str, Any],
        k: int = 5
    ) -> str:
        """Build prompt from strategy and question data."""
        copyable_text = question_data.get("copyable_text") or question_data.get("latex_stem_text", "")
        prefix_note = question_data.get("prompt_prefix_note") or ""
        answer_guidance = question_data.get("answer_guidance") or ""
        retry_instructions = question_data.get("retry_instructions") or ""

        return strategy.prompt_template.format(
            question_index=question_data.get("question_number", ""),
            latex_stem_text=question_data.get("latex_stem_text", ""),
            gold_answer=question_data.get("gold_answer", ""),
            question_type=question_data.get("question_type", ""),
            options=self._format_options(question_data.get("options")),
            k=k,
            reasoning_steps="\n".join(f"- {step}" for step in strategy.reasoning_steps),
            copyable_text=copyable_text,
            prefix_note=prefix_note,
            answer_guidance=answer_guidance,
            retry_instructions=retry_instructions,
        )


# Global registry instance
_strategy_registry = None


def get_strategy_registry() -> StrategyRegistry:
    """Get global strategy registry."""
    global _strategy_registry
    if _strategy_registry is None:
        _strategy_registry = StrategyRegistry()
    return _strategy_registry
