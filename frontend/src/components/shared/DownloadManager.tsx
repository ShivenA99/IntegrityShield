import React from "react";

interface DownloadManagerProps {
  items: { label: string; onDownload: () => void }[];
}

const DownloadManager: React.FC<DownloadManagerProps> = ({ items }) => (
  <div className="download-manager">
    <h3>Downloads</h3>
    <ul>
      {items.map((item) => (
        <li key={item.label}>
          <button onClick={item.onDownload}>{item.label}</button>
        </li>
      ))}
    </ul>
  </div>
);

export default DownloadManager;
