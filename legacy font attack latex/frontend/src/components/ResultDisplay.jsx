import React from 'react'
import './ResultDisplay.css'

export default function ResultDisplay({ result, loading, apiUrl }) {
  if (loading) {
    return (
      <div className="result-display">
        <div className="loading-state">
          <div className="loading-spinner"></div>
          <p>Generating manipulated PDF...</p>
          <p className="loading-detail">This may take a few seconds</p>
        </div>
      </div>
    )
  }

  if (!result) {
    return (
      <div className="result-display">
        <div className="empty-state">
          <div className="empty-icon">📄</div>
          <h3>No Results Yet</h3>
          <p>Configure your manipulation and click "Generate PDF" to get started.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="result-display">
      <div className="success-state">
        <div className="success-header">
          <div className="success-icon">✓</div>
          <div>
            <h3>Manipulation Successful!</h3>
            <p className="success-mode">Mode: {result.mode}</p>
          </div>
        </div>

        <div className="download-section">
          <h4>Download Files</h4>

          <a
            href={`${apiUrl}/download/${result.pdf_file}`}
            className="download-btn pdf"
            download
          >
            <span className="file-icon">📄</span>
            <div className="file-info">
              <span className="file-name">PDF Document</span>
              <span className="file-detail">{result.pdf_file}</span>
            </div>
            <span className="download-icon">⬇</span>
          </a>

          {result.font_file && (
            <a
              href={`${apiUrl}/download/${result.font_file}`}
              className="download-btn font"
              download
            >
              <span className="file-icon">🔤</span>
              <div className="file-info">
                <span className="file-name">Font File</span>
                <span className="file-detail">{result.font_file}</span>
              </div>
              <span className="download-icon">⬇</span>
            </a>
          )}
        </div>

        <div className="instructions">
          <h4>How to Test</h4>
          <ol>
            <li>Download and open the PDF file</li>
            <li>Locate the <span className="highlight">RED</span> word in the document</li>
            <li>Select and copy the RED word</li>
            <li>Paste into a text editor</li>
            <li>Observe that the copied text differs from what you see!</li>
          </ol>
        </div>

        <div className="info-box">
          <div className="info-icon">ℹ️</div>
          <div>
            <strong>Educational Purpose Only</strong>
            <p>This tool is for security research and defensive purposes. Do not use for malicious activities.</p>
          </div>
        </div>
      </div>
    </div>
  )
}
