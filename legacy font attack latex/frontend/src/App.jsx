import React, { useState, useEffect } from 'react'
import axios from 'axios'
import './App.css'
import ManipulationForm from './components/ManipulationForm'
import ModeSelector from './components/ModeSelector'
import ResultDisplay from './components/ResultDisplay'

const API_URL = 'http://localhost:5001/api'

function App() {
  const [modes, setModes] = useState([])
  const [selectedMode, setSelectedMode] = useState('truly_selective')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [healthStatus, setHealthStatus] = useState(null)

  useEffect(() => {
    // Load modes and check health
    const init = async () => {
      try {
        const [modesRes, healthRes] = await Promise.all([
          axios.get(`${API_URL}/modes`),
          axios.get(`${API_URL}/health`)
        ])
        setModes(modesRes.data.modes)
        setHealthStatus(healthRes.data)
      } catch (err) {
        setError('Failed to connect to backend. Make sure Flask server is running on port 5001.')
      }
    }
    init()
  }, [])

  const handleManipulate = async (visualWord, hiddenWord) => {
    setLoading(true)
    setError(null)
    setResult(null)

    try {
      const response = await axios.post(`${API_URL}/manipulate`, {
        mode: selectedMode,
        visual_word: visualWord,
        hidden_word: hiddenWord
      })

      setResult(response.data)
    } catch (err) {
      setError(err.response?.data?.error || 'Manipulation failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="app">
      <div className="container">
        <header className="header">
          <h1>🔤 Font Manipulation Tool</h1>
          <p className="subtitle">Create deceptive PDFs using font manipulation techniques</p>
          <p className="paper-ref">Based on arXiv:2505.16957</p>

          {healthStatus && (
            <div className="health-status">
              <span className="status-dot"></span>
              Backend Connected (v{healthStatus.version})
            </div>
          )}
        </header>

        {error && (
          <div className="error-banner">
            <span>⚠️</span>
            <span>{error}</span>
          </div>
        )}

        <div className="content">
          <div className="left-panel">
            <ModeSelector
              modes={modes}
              selectedMode={selectedMode}
              onSelectMode={setSelectedMode}
            />

            <ManipulationForm
              onSubmit={handleManipulate}
              loading={loading}
              selectedMode={selectedMode}
            />
          </div>

          <div className="right-panel">
            <ResultDisplay
              result={result}
              loading={loading}
              apiUrl={API_URL}
            />
          </div>
        </div>
      </div>
    </div>
  )
}

export default App
