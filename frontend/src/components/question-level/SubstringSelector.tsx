import React from "react";

interface SubstringSelectorProps {
  text: string;
  onSelect: (range: { start: number; end: number }) => void;
}

const SubstringSelector: React.FC<SubstringSelectorProps> = ({ text }) => {
  return (
    <div className="substring-selector">
      <pre>{text}</pre>
      <p>Select text in the PDF viewer to create substitutions.</p>
    </div>
  );
};

export default SubstringSelector;
