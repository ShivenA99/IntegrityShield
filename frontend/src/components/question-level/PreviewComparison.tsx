import React from "react";

interface PreviewComparisonProps {
  original: string;
  manipulated: string;
}

const PreviewComparison: React.FC<PreviewComparisonProps> = ({ original, manipulated }) => (
  <div className="preview-comparison">
    <div>
      <h4>Original</h4>
      <pre>{original}</pre>
    </div>
    <div>
      <h4>Manipulated</h4>
      <pre>{manipulated}</pre>
    </div>
  </div>
);

export default PreviewComparison;
