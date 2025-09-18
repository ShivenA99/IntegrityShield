#!/usr/bin/env python3
"""
Input Validation Module for Malicious Font Pipeline
Handles input processing, validation, and compatibility checking.
"""

import re
import logging
from typing import Dict, List, Tuple, Optional

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class InputValidator:
    """
    Validates and processes input parameters for the malicious font pipeline.
    """
    
    def __init__(self):
        self.min_length = 1
        self.max_length = 100
        # Allow printable ASCII and common punctuation in input string
        self.allowed_chars = re.compile(r'^[\x20-\x7E]+$')
    
    def validate_input_string(self, text: str) -> bool:
        """
        Validate the input string for PDF generation.
        
        Args:
            text (str): The input text to validate
        
        Returns:
            bool: True if valid, False otherwise
        """
        if not text or not isinstance(text, str):
            logger.error("Input string must be a non-empty string")
            return False
        
        if len(text) < self.min_length or len(text) > self.max_length:
            logger.error(f"Input string length must be between {self.min_length} and {self.max_length} characters")
            return False
        
        if not self.allowed_chars.match(text):
            logger.error("Input string contains invalid characters (non-printable ASCII)")
            return False
        
        logger.info(f"✓ Input string validated: '{text}'")
        return True
    
    def validate_entity(self, entity: str) -> bool:
        """
        Validate an entity (word) for font manipulation.
        
        Args:
            entity (str): The entity to validate
        
        Returns:
            bool: True if valid, False otherwise
        """
        if not entity or not isinstance(entity, str):
            logger.error("Entity must be a non-empty string")
            return False
        
        if len(entity) < 1 or len(entity) > 50:
            logger.error("Entity length must be between 1 and 50 characters")
            return False
        
        # v2 charset: printable ASCII (space to ~)
        if not re.match(r'^[\x20-\x7E]+$', entity):
            logger.error("Entity must contain only printable ASCII characters (space..~)")
            return False
        
        logger.info(f"✓ Entity validated: '{entity}'")
        return True
    
    def validate_mapping(self, input_entity: str, output_entity: str) -> bool:
        """
        Validate the mapping between input and output entities.
        
        Args:
            input_entity (str): The input entity
            output_entity (str): The output entity
        
        Returns:
            bool: True if valid, False otherwise
        """
        if not self.validate_entity(input_entity):
            return False
        
        if not self.validate_entity(output_entity):
            return False
        
        if input_entity == output_entity:
            logger.error("Input and output entities cannot be the same")
            return False
        
        logger.info(f"✓ Mapping validated: '{input_entity}' → '{output_entity}'")
        return True
    
    def check_compatibility(self, input_entity: str, output_entity: str) -> Dict:
        """
        Check compatibility between input and output entities.
        
        Args:
            input_entity (str): The input entity
            output_entity (str): The output entity
        
        Returns:
            Dict: Compatibility analysis including duplicate handling strategy
        """
        if not self.validate_mapping(input_entity, output_entity):
            return {"compatible": False, "error": "Invalid mapping"}
        
        analysis = {
            "compatible": True,
            "input_entity": input_entity,
            "output_entity": output_entity,
            "input_length": len(input_entity),
            "output_length": len(output_entity),
            "duplicates": self._find_duplicates(input_entity),
            "mapping_strategy": self._create_mapping_strategy(input_entity, output_entity)
        }
        
        logger.info(f"✓ Compatibility analysis completed for '{input_entity}' → '{output_entity}'")
        return analysis
    
    def _find_duplicates(self, entity: str) -> List[Dict]:
        """
        Find duplicate characters in an entity.
        
        Args:
            entity (str): The entity to analyze
        
        Returns:
            List[Dict]: List of duplicate character information
        """
        duplicates = []
        char_count = {}
        
        for i, char in enumerate(entity):
            if char in char_count:
                char_count[char].append(i)
            else:
                char_count[char] = [i]
        
        for char, positions in char_count.items():
            if len(positions) > 1:
                duplicates.append({
                    "character": char,
                    "positions": positions,
                    "count": len(positions)
                })
        
        if duplicates:
            logger.info(f"Found {len(duplicates)} duplicate character(s) in '{entity}'")
        else:
            logger.info(f"No duplicates found in '{entity}'")
        
        return duplicates
    
    def _create_mapping_strategy(self, input_entity: str, output_entity: str) -> Dict:
        """
        Create a mapping strategy for the entities.
        
        Args:
            input_entity (str): The input entity
            output_entity (str): The output entity
        
        Returns:
            Dict: Mapping strategy information
        """
        # Create basic character mapping
        basic_mapping = {}
        min_length = min(len(input_entity), len(output_entity))
        
        for i in range(min_length):
            input_char = input_entity[i]
            output_char = output_entity[i]
            if input_char != output_char:
                basic_mapping[input_char] = output_char
        
        # Handle length differences
        if len(input_entity) > len(output_entity):
            strategy = "truncate"
        elif len(input_entity) < len(output_entity):
            strategy = "extend"
        else:
            strategy = "direct"
        
        return {
            "basic_mapping": basic_mapping,
            "strategy": strategy,
            "input_length": len(input_entity),
            "output_length": len(output_entity),
            "mapping_changes": len(basic_mapping)
        }

def validate_pipeline_inputs(input_string: str, input_entity: str, output_entity: str) -> Tuple[bool, Optional[Dict]]:
    """
    Validate all pipeline inputs.
    
    Args:
        input_string (str): The complete input text
        input_entity (str): The entity to attack
        output_entity (str): The desired visual output
    
    Returns:
        Tuple[bool, Optional[Dict]]: (is_valid, compatibility_analysis)
    """
    validator = InputValidator()
    
    # Validate individual inputs
    if not validator.validate_input_string(input_string):
        return False, None
    
    if not validator.validate_entity(input_entity):
        return False, None
    
    if not validator.validate_entity(output_entity):
        return False, None
    
    # Check if input entity exists in input string
    if input_entity not in input_string:
        logger.error(f"Input entity '{input_entity}' not found in input string")
        return False, None
    
    # Check compatibility
    compatibility = validator.check_compatibility(input_entity, output_entity)
    
    if not compatibility["compatible"]:
        return False, None
    
    logger.info("✓ All pipeline inputs validated successfully")
    return True, compatibility

if __name__ == "__main__":
    # Test the validator
    test_cases = [
        ("What is the capital of Russia?", "Russia", "Canada"),
        ("Hello World", "World", "Earth"),
        ("Test", "Test", "Test"),  # Should fail
        ("", "Word", "Other"),  # Should fail
    ]
    
    for input_string, input_entity, output_entity in test_cases:
        print(f"\nTesting: '{input_string}' | '{input_entity}' → '{output_entity}'")
        is_valid, analysis = validate_pipeline_inputs(input_string, input_entity, output_entity)
        print(f"Valid: {is_valid}")
        if analysis:
            print(f"Analysis: {analysis}") 