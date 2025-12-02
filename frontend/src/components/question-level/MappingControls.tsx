import React from "react";

interface MappingControlsProps {
  onStrategyChange?: (strategy: string) => void;
}

const MappingControls: React.FC<MappingControlsProps> = ({ onStrategyChange }) => {
  return (
    <div className="mapping-controls">
      <label htmlFor="strategy">Strategy</label>
      <select id="strategy" onChange={(event) => onStrategyChange?.(event.target.value)}>
        <option value="unicode_steganography">Unicode Steganography</option>
        <option value="mathematical_variants">Mathematical Variants</option>
        <option value="fullwidth_forms">Fullwidth Forms</option>
        <option value="custom">Custom Mapping</option>
      </select>
    </div>
  );
};

export default MappingControls;
