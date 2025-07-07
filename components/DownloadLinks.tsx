import React from 'react';

interface DownloadLinksProps {
  assessmentId: string;
}

export const DownloadLinks: React.FC<DownloadLinksProps> = ({ assessmentId }) => {
  const attackedUrl = `/api/assessments/${assessmentId}/attacked`;
  const reportUrl = `/api/assessments/${assessmentId}/report`;
  return (
    <div className="space-y-4">
      <a
        href={attackedUrl}
        className="block w-full text-center px-6 py-3 bg-emerald-600 text-white font-semibold rounded-lg shadow hover:bg-emerald-700 transition"
      >
        Download Attacked PDF
      </a>
      <a
        href={reportUrl}
        className="block w-full text-center px-6 py-3 bg-indigo-600 text-white font-semibold rounded-lg shadow hover:bg-indigo-700 transition"
      >
        Download Reference Report
      </a>
    </div>
  );
}; 