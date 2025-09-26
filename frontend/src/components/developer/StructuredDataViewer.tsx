import React from "react";
interface StructuredDataViewerProps {
  data: Record<string, unknown> | null | undefined;
}

const StructuredDataViewer: React.FC<StructuredDataViewerProps> = ({ data }) => (
  <div className="structured-data-viewer">
    <h3>Structured Data</h3>
    <pre style={{ maxHeight: 360, overflow: "auto" }}>
      {JSON.stringify(data ?? {}, null, 2)}
    </pre>
  </div>
);

export default StructuredDataViewer;
