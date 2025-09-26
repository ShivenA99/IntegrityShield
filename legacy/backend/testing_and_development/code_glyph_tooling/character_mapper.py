#!/usr/bin/env python3
"""
Character Mapping Analyzer for Malicious Font Pipeline
Handles complex character mappings and generates optimal font strategies.
"""

import logging
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from input_validator import InputValidator

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class DuplicateInfo:
    """Information about duplicate characters in an entity."""
    character: str
    positions: List[int]
    count: int
    output_mappings: List[str]

@dataclass
class FontStrategy:
    """Strategy for creating a malicious font."""
    font_id: int
    character_mappings: Dict[str, str]
    apply_positions: List[int]
    priority: int
    description: str

@dataclass
class MappingAnalysis:
    """Complete analysis of character mapping requirements."""
    input_entity: str
    output_entity: str
    character_mappings: Dict[str, str]
    duplicate_positions: List[DuplicateInfo]
    required_fonts: int
    font_strategies: List[FontStrategy]
    basic_mapping: Dict[str, str]
    strategy_type: str

class CharacterMapper:
    """
    Analyzes character mappings and generates optimal font strategies.
    """
    
    def __init__(self):
        self.validator = InputValidator()
    
    def analyze_mapping(self, input_entity: str, output_entity: str) -> MappingAnalysis:
        """
        Analyze the mapping between input and output entities.
        
        Args:
            input_entity (str): The input entity
            output_entity (str): The output entity
            
        Returns:
            MappingAnalysis: Complete mapping analysis
        """
        logger.info(f"Analyzing mapping: '{input_entity}' → '{output_entity}'")
        
        # Validate inputs
        if not self.validator.validate_mapping(input_entity, output_entity):
            raise ValueError("Invalid mapping provided")
        
        # Get compatibility analysis
        compatibility = self.validator.check_compatibility(input_entity, output_entity)
        
        # Find duplicates
        duplicates = self._analyze_duplicates(input_entity, output_entity)
        
        # Create character mappings
        character_mappings = self._create_character_mappings(input_entity, output_entity)
        
        # Generate font strategies
        font_strategies = self._generate_font_strategies(input_entity, output_entity, duplicates)
        
        # Determine strategy type
        strategy_type = self._determine_strategy_type(input_entity, output_entity, duplicates)
        
        analysis = MappingAnalysis(
            input_entity=input_entity,
            output_entity=output_entity,
            character_mappings=character_mappings,
            duplicate_positions=duplicates,
            required_fonts=len(font_strategies),
            font_strategies=font_strategies,
            basic_mapping=compatibility["mapping_strategy"]["basic_mapping"],
            strategy_type=strategy_type
        )
        
        logger.info(f"✓ Mapping analysis completed: {len(font_strategies)} font(s) required")
        return analysis
    
    def _analyze_duplicates(self, input_entity: str, output_entity: str) -> List[DuplicateInfo]:
        """
        Analyze duplicate characters and their required mappings.
        
        Args:
            input_entity (str): The input entity
            output_entity (str): The output entity
            
        Returns:
            List[DuplicateInfo]: List of duplicate character information
        """
        duplicates = []
        char_positions = {}
        
        # Find all character positions
        for i, char in enumerate(input_entity):
            if char not in char_positions:
                char_positions[char] = []
            char_positions[char].append(i)
        
        # Analyze duplicates
        for char, positions in char_positions.items():
            if len(positions) > 1:
                # For duplicates, we need different output mappings
                output_mappings = []
                for pos in positions:
                    if pos < len(output_entity):
                        output_mappings.append(output_entity[pos])
                    else:
                        output_mappings.append(char)  # Keep original if output is shorter
                
                duplicate_info = DuplicateInfo(
                    character=char,
                    positions=positions,
                    count=len(positions),
                    output_mappings=output_mappings
                )
                duplicates.append(duplicate_info)
        
        logger.info(f"Found {len(duplicates)} duplicate character(s) requiring special handling")
        return duplicates
    
    def _create_character_mappings(self, input_entity: str, output_entity: str) -> Dict[str, str]:
        """
        Create basic character mappings.
        
        Args:
            input_entity (str): The input entity
            output_entity (str): The output entity
            
        Returns:
            Dict[str, str]: Character mappings
        """
        mappings = {}
        min_length = min(len(input_entity), len(output_entity))
        
        for i in range(min_length):
            input_char = input_entity[i]
            output_char = output_entity[i]
            if input_char != output_char:
                mappings[input_char] = output_char
        
        logger.info(f"Created {len(mappings)} character mapping(s)")
        return mappings
    
    def _generate_font_strategies(self, input_entity: str, output_entity: str, duplicates: List[DuplicateInfo]) -> List[FontStrategy]:
        """
        Generate optimal font strategies for the mapping.
        
        Args:
            input_entity (str): The input entity
            output_entity (str): The output entity
            duplicates (List[DuplicateInfo]): Duplicate character information
            
        Returns:
            List[FontStrategy]: List of font strategies
        """
        strategies = []
        
        if not duplicates:
            # Simple case: single font
            basic_mapping = self._create_character_mappings(input_entity, output_entity)
            strategy = FontStrategy(
                font_id=1,
                character_mappings=basic_mapping,
                apply_positions=list(range(len(input_entity))),
                priority=1,
                description=f"Single font mapping for '{input_entity}' → '{output_entity}'"
            )
            strategies.append(strategy)
        else:
            # Complex case: multiple fonts for duplicates
            strategies = self._create_multi_font_strategy(input_entity, output_entity, duplicates)
        
        logger.info(f"Generated {len(strategies)} font strategy(ies)")
        return strategies
    
    def _create_multi_font_strategy(self, input_entity: str, output_entity: str, duplicates: List[DuplicateInfo]) -> List[FontStrategy]:
        """
        Create optimal font strategies for handling duplicates.
        
        Args:
            input_entity (str): The input entity
            output_entity (str): The output entity
            duplicates (List[DuplicateInfo]): Duplicate character information
            
        Returns:
            List[FontStrategy]: List of font strategies
        """
        logger.info("=" * 60)
        logger.info("🔍 CREATING OPTIMAL FONT STRATEGIES")
        logger.info("=" * 60)
        logger.info(f"Input Entity: '{input_entity}'")
        logger.info(f"Output Entity: '{output_entity}'")
        logger.info(f"Duplicates Found: {len(duplicates)}")
        
        strategies = []
        
        # Step 1: Analyze all character positions and their target mappings
        position_analysis = {}
        logger.info("\n📊 STEP 1: POSITION ANALYSIS")
        logger.info("-" * 40)
        
        for i, input_char in enumerate(input_entity):
            if i < len(output_entity):
                output_char = output_entity[i]
                if input_char != output_char:
                    position_analysis[i] = (input_char, output_char)
                    logger.info(f"Position {i}: '{input_char}' → '{output_char}'")
                else:
                    logger.info(f"Position {i}: '{input_char}' → '{input_char}' (no mapping needed)")
            else:
                logger.info(f"Position {i}: '{input_char}' → (output too short)")
        
        # Step 2: Create optimal font combinations
        logger.info("\n🎨 STEP 2: CREATING OPTIMAL FONT COMBINATIONS")
        logger.info("-" * 40)
        
        if not duplicates:
            # Simple case: single font
            logger.info("No duplicates found - creating single font")
            all_mappings = {input_char: output_char for i, (input_char, output_char) in position_analysis.items()}
            strategy = FontStrategy(
                font_id=1,
                character_mappings=all_mappings,
                apply_positions=list(position_analysis.keys()),
                priority=1,
                description=f"Single font for '{input_entity}' → '{output_entity}'"
            )
            strategies.append(strategy)
            logger.info(f"✓ Created 1 font with {len(all_mappings)} mappings")
        else:
            # Complex case: multiple fonts for duplicates
            logger.info(f"Found {len(duplicates)} duplicate character(s) - creating optimal font combination")
            
            # Create base font with all mappings except the last occurrence of each duplicate
            base_mapping = {}
            base_positions = []
            duplicate_fonts = {}
            
            # Group duplicate positions by their target output
            for dup in duplicates:
                char = dup.character
                positions = dup.positions
                logger.info(f"\nAnalyzing duplicate '{char}' at positions {positions}")
                
                # Find target outputs for each position
                for pos in positions:
                    if pos in position_analysis:
                        input_char, output_char = position_analysis[pos]
                        if input_char == char:
                            if output_char not in duplicate_fonts:
                                duplicate_fonts[output_char] = []
                            duplicate_fonts[output_char].append(pos)
                            logger.info(f"  Position {pos}: '{char}' → '{output_char}'")
            
            # Create base font (all mappings except the LAST occurrence of each duplicate)
            logger.info("\n📝 Creating base font:")
            for i, (input_char, output_char) in position_analysis.items():
                # Check if this is the LAST occurrence of a duplicate character
                is_last_duplicate = False
                for dup in duplicates:
                    if input_char == dup.character and i == dup.positions[-1]:  # Last position
                        is_last_duplicate = True
                        logger.info(f"  Position {i}: '{input_char}' → '{output_char}' (LAST DUPLICATE - exclude from base)")
                        break
                
                if not is_last_duplicate:
                    # Add to base mapping - this will handle the FIRST occurrence of each character
                    base_mapping[input_char] = output_char
                    base_positions.append(i)
                    logger.info(f"  Position {i}: '{input_char}' → '{output_char}' (ADDED TO BASE - first occurrence)")
            
            # Create base font strategy
            if base_mapping:
                base_strategy = FontStrategy(
                    font_id=1,
                    character_mappings=base_mapping,
                    apply_positions=base_positions,
                    priority=1,
                    description=f"Base font for '{input_entity}' → '{output_entity}' (excluding last duplicate occurrence)"
                )
                strategies.append(base_strategy)
                logger.info(f"✓ Created base font with {len(base_mapping)} mappings for positions {base_positions}")
            
            # Create duplicate-specific fonts
            logger.info("\n🎯 Creating duplicate-specific fonts:")
            
            # Collect all remaining mappings that need separate fonts
            remaining_mappings = {}
            
            # For each duplicate character, collect the remaining occurrences
            for dup in duplicates:
                char = dup.character
                positions = dup.positions
                
                # Group positions by their target output
                output_groups = {}
                for pos in positions:
                    if pos in position_analysis:
                        input_char, output_char = position_analysis[pos]
                        if input_char == char:
                            if output_char not in output_groups:
                                output_groups[output_char] = []
                            output_groups[output_char].append(pos)
                
                # Check if this mapping is already in the base font
                for output_char, pos_list in output_groups.items():
                    base_has_mapping = False
                    if char in base_mapping and base_mapping[char] == output_char:
                        base_has_mapping = True
                    
                    if base_has_mapping:
                        # This mapping is in the base font, so we need fonts for all remaining positions
                        remaining_positions = pos_list[1:]  # All positions except the first
                        
                        if remaining_positions:
                            # Add to remaining mappings
                            if output_char not in remaining_mappings:
                                remaining_mappings[output_char] = {}
                            remaining_mappings[output_char][char] = remaining_positions
                            logger.info(f"✓ Added remaining mapping: '{char}' → '{output_char}' at positions {remaining_positions}")
                    else:
                        # This mapping is NOT in the base font, so we need fonts for ALL positions
                        if output_char not in remaining_mappings:
                            remaining_mappings[output_char] = {}
                        remaining_mappings[output_char][char] = pos_list
                        logger.info(f"✓ Added complete mapping: '{char}' → '{output_char}' at positions {pos_list}")
            
            # Create optimized fonts by grouping non-conflicting mappings
            font_id = len(strategies) + 1
            for output_char, char_mappings in remaining_mappings.items():
                # Create a single font for all mappings to this output character
                combined_mappings = {}
                combined_positions = []
                
                for char, positions in char_mappings.items():
                    combined_mappings[char] = output_char
                    combined_positions.extend(positions)
                
                dup_strategy = FontStrategy(
                    font_id=font_id,
                    character_mappings=combined_mappings,
                    apply_positions=combined_positions,
                    priority=2,
                    description=f"Duplicate font for mappings to '{output_char}' at positions {combined_positions}"
                )
                strategies.append(dup_strategy)
                logger.info(f"✓ Created optimized duplicate font {font_id}: {combined_mappings} at positions {combined_positions}")
                font_id += 1
        
        # Step 3: Validate font strategies
        logger.info("\n✅ STEP 3: VALIDATION")
        logger.info("-" * 40)
        logger.info(f"Total fonts created: {len(strategies)}")
        
        for i, strategy in enumerate(strategies, 1):
            logger.info(f"Font {i}: {strategy.description}")
            logger.info(f"  Mappings: {strategy.character_mappings}")
            logger.info(f"  Positions: {strategy.apply_positions}")
            logger.info(f"  Priority: {strategy.priority}")
        
        # Check for conflicts
        all_positions = set()
        for strategy in strategies:
            for pos in strategy.apply_positions:
                if pos in all_positions:
                    logger.warning(f"⚠️  CONFLICT: Position {pos} appears in multiple fonts!")
                all_positions.add(pos)
        
        logger.info(f"✓ All positions covered: {sorted(all_positions)}")
        logger.info("=" * 60)
        
        return strategies
    
    def _determine_strategy_type(self, input_entity: str, output_entity: str, duplicates: List[DuplicateInfo]) -> str:
        """
        Determine the type of mapping strategy required.
        
        Args:
            input_entity (str): The input entity
            output_entity (str): The output entity
            duplicates (List[DuplicateInfo]): Duplicate character information
            
        Returns:
            str: Strategy type
        """
        if not duplicates:
            return "single_font"
        elif len(duplicates) == 1 and duplicates[0].count == 2:
            return "duplicate_simple"
        else:
            return "duplicate_complex"
    
    def get_mapping_summary(self, analysis: MappingAnalysis) -> Dict:
        """
        Get a summary of the mapping analysis.
        
        Args:
            analysis (MappingAnalysis): The mapping analysis
            
        Returns:
            Dict: Summary information
        """
        summary = {
            "input_entity": analysis.input_entity,
            "output_entity": analysis.output_entity,
            "strategy_type": analysis.strategy_type,
            "required_fonts": analysis.required_fonts,
            "character_mappings": analysis.character_mappings,
            "duplicates": len(analysis.duplicate_positions),
            "font_strategies": []
        }
        
        for strategy in analysis.font_strategies:
            summary["font_strategies"].append({
                "font_id": strategy.font_id,
                "mappings": strategy.character_mappings,
                "positions": strategy.apply_positions,
                "description": strategy.description
            })
        
        return summary

def analyze_entity_mapping(input_entity: str, output_entity: str) -> MappingAnalysis:
    """
    Analyze the mapping between two entities.
    
    Args:
        input_entity (str): The input entity
        output_entity (str): The output entity
        
    Returns:
        MappingAnalysis: Complete mapping analysis
    """
    mapper = CharacterMapper()
    return mapper.analyze_mapping(input_entity, output_entity)

if __name__ == "__main__":
    # Test the character mapper
    test_cases = [
        ("Russia", "Canada"),
        ("Hello", "World"),
        ("Test", "Exam"),
        ("Mississippi", "California"),
    ]
    
    for input_entity, output_entity in test_cases:
        print(f"\nAnalyzing: '{input_entity}' → '{output_entity}'")
        try:
            analysis = analyze_entity_mapping(input_entity, output_entity)
            summary = CharacterMapper().get_mapping_summary(analysis)
            print(f"Strategy: {summary['strategy_type']}")
            print(f"Fonts required: {summary['required_fonts']}")
            print(f"Duplicates: {summary['duplicates']}")
        except Exception as e:
            print(f"Error: {e}") 