import * as React from "react";

interface OptionCardProps {
  label: string;
  text: string;
  isCorrect?: boolean;
  isSelected?: boolean;
}

const OptionCard: React.FC<OptionCardProps> = ({
  label,
  text,
  isCorrect = false,
  isSelected = false
}) => {
  return (
    <div
      className="option-card"
      data-correct={isCorrect}
      data-selected={isSelected}
    >
      <span className="option-label">{label}</span>
      <span className="option-text">{text}</span>
    </div>
  );
};

export default OptionCard;
