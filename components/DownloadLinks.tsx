import React from 'react';

interface DownloadLinksProps {
  assessmentId: string;
}

export const DownloadLinks: React.FC<DownloadLinksProps> = ({ assessmentId }) => {
  // Add timestamp to force fresh downloads and bypass cache
  const timestamp = Date.now();
  const attackedUrl = `/api/assessments/${assessmentId}/attacked?t=${timestamp}`;
  const reportUrl = `/api/assessments/${assessmentId}/report?t=${timestamp}`;
  return (
    <div className="space-y-4">
      <a
        href={attackedUrl}
        download
        className="block w-full text-center px-6 py-3 bg-emerald-600 text-white font-semibold rounded-lg shadow hover:bg-emerald-700 transition"
      >
        Download Attacked PDF
      </a>
      <a
        href={reportUrl}
        download
        className="block w-full text-center px-6 py-3 bg-indigo-600 text-white font-semibold rounded-lg shadow hover:bg-indigo-700 transition"
      >
        Download Reference Report
      </a>
    </div>
  );
}; 