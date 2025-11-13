import React from 'react'
import './ModeSelector.css'

export default function ModeSelector({ modes, selectedMode, onSelectMode }) {
  return (
    <div className="mode-selector">
      <h2>Manipulation Mode</h2>

      <div className="modes-grid">
        {modes.map((mode) => (
          <div
            key={mode.id}
            className={`mode-card ${selectedMode === mode.id ? 'selected' : ''}`}
            onClick={() => onSelectMode(mode.id)}
          >
            <div className="mode-header">
              <h3>{mode.name}</h3>
              {selectedMode === mode.id && <span className="check">✓</span>}
            </div>

            <p className="mode-description">{mode.description}</p>

            <div className="mode-badges">
              <div className="badge-group">
                <span className="badge-label">Pros:</span>
                {mode.pros.map((pro, idx) => (
                  <span key={idx} className="badge pro">{pro}</span>
                ))}
              </div>

              <div className="badge-group">
                <span className="badge-label">Cons:</span>
                {mode.cons.map((con, idx) => (
                  <span key={idx} className="badge con">{con}</span>
                ))}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
