import * as React from "react";

interface MappingCardProps {
  context: string;
  original: string;
  replacement: string;
  deviationScore?: number;
  validated?: boolean;
}

const MappingCard: React.FC<MappingCardProps> = ({
  context,
  original,
  replacement,
  deviationScore,
  validated = false
}) => {
  return (
    <div className="mapping-card" data-validated={validated}>
      <div className="mapping-header">
        <span className="context">{context}</span>
        {deviationScore !== undefined && (
          <span className="deviation-score">
            {deviationScore.toFixed(2)}
          </span>
        )}
      </div>
      <div className="mapping-content">
        <span className="original">{original}</span>
        <span className="arrow">→</span>
        <span className="replacement">{replacement}</span>
      </div>
      {validated && (
        <span className="validation-badge">✓ Validated</span>
      )}
    </div>
  );
};

export default MappingCard;
