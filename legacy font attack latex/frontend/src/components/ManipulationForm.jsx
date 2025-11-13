import React, { useState } from 'react'
import './ManipulationForm.css'

const EXAMPLES = [
  { visual: 'hello', hidden: 'world' },
  { visual: 'login', hidden: 'admin' },
  { visual: 'click', hidden: 'trap!' },
  { visual: 'safe!', hidden: 'hack!' },
]

export default function ManipulationForm({ onSubmit, loading, selectedMode }) {
  const [visualWord, setVisualWord] = useState('hello')
  const [hiddenWord, setHiddenWord] = useState('world')
  const [error, setError] = useState('')

  const handleSubmit = (e) => {
    e.preventDefault()
    setError('')

    if (!visualWord || !hiddenWord) {
      setError('Both words are required')
      return
    }

    if (visualWord.length !== hiddenWord.length) {
      setError('Words must be the same length')
      return
    }

    onSubmit(visualWord, hiddenWord)
  }

  const loadExample = (example) => {
    setVisualWord(example.visual)
    setHiddenWord(example.hidden)
    setError('')
  }

  return (
    <div className="manipulation-form">
      <h2>Configure Manipulation</h2>

      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label htmlFor="visual">
            Visual Word
            <span className="help-text">What the user sees</span>
          </label>
          <input
            id="visual"
            type="text"
            value={visualWord}
            onChange={(e) => setVisualWord(e.target.value)}
            placeholder="e.g., hello"
            disabled={loading}
          />
        </div>

        <div className="form-group">
          <label htmlFor="hidden">
            Hidden Word
            <span className="help-text">What gets copied/extracted</span>
          </label>
          <input
            id="hidden"
            type="text"
            value={hiddenWord}
            onChange={(e) => setHiddenWord(e.target.value)}
            placeholder="e.g., world"
            disabled={loading}
          />
        </div>

        <div className="length-indicator">
          <span>Visual: {visualWord.length} chars</span>
          <span>Hidden: {hiddenWord.length} chars</span>
          {visualWord.length === hiddenWord.length && visualWord.length > 0 ? (
            <span className="match">✓ Match</span>
          ) : (
            <span className="mismatch">✗ Mismatch</span>
          )}
        </div>

        {error && (
          <div className="form-error">
            {error}
          </div>
        )}

        <button
          type="submit"
          className="submit-btn"
          disabled={loading || visualWord.length !== hiddenWord.length}
        >
          {loading ? (
            <>
              <span className="spinner"></span>
              Generating...
            </>
          ) : (
            <>
              <span>🔨</span>
              Generate PDF
            </>
          )}
        </button>
      </form>

      <div className="examples">
        <h3>Examples</h3>
        <div className="examples-grid">
          {EXAMPLES.map((example, idx) => (
            <button
              key={idx}
              onClick={() => loadExample(example)}
              className="example-btn"
              disabled={loading}
            >
              <span className="visual">{example.visual}</span>
              <span className="arrow">→</span>
              <span className="hidden">{example.hidden}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
