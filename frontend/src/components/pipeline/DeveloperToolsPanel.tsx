import * as React from "react";
import { useState, useEffect, useCallback } from "react";

import { usePipeline } from "@hooks/usePipeline";

interface LogEntry {
  timestamp: string;
  level: string;
  stage: string;
  component: string;
  message: string;
  metadata?: any;
}

interface PerformanceMetric {
  stage: string;
  metric_name: string;
  metric_value: number;
  metric_unit: string;
  metadata?: any;
  recorded_at: string;
}

interface AIClientStatus {
  openai_vision: { configured: boolean; available: boolean };
  mistral_ocr: { configured: boolean; available: boolean };
  gpt5_fusion: { configured: boolean; available: boolean };
}

interface SystemHealth {
  status: string;
  database: boolean;
  ai_clients: AIClientStatus;
  storage: boolean;
  websockets: boolean;
}

const DeveloperToolsPanel: React.FC = () => {
  const { activeRunId } = usePipeline();
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [metrics, setMetrics] = useState<PerformanceMetric[]>([]);
  const [aiClients, setAiClients] = useState<AIClientStatus | null>(null);
  const [systemHealth, setSystemHealth] = useState<SystemHealth | null>(null);
  const [structuredData, setStructuredData] = useState<any>(null);
  const [activeTab, setActiveTab] = useState<'logs' | 'metrics' | 'ai-status' | 'health' | 'data'>('logs');
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [isLoading, setIsLoading] = useState(false);

  const fetchLogs = useCallback(async () => {
    if (!activeRunId) return;
    try {
      const response = await fetch(`/api/developer/${activeRunId}/logs`);
      if (response.ok) {
        const data = await response.json();
        setLogs(data.logs);
      }
    } catch (error) {
      console.error('Error fetching logs:', error);
    }
  }, [activeRunId]);

  const fetchMetrics = useCallback(async () => {
    if (!activeRunId) return;
    try {
      const response = await fetch(`/api/developer/${activeRunId}/metrics`);
      if (response.ok) {
        const data = await response.json();
        setMetrics(data.metrics);
      }
    } catch (error) {
      console.error('Error fetching metrics:', error);
    }
  }, [activeRunId]);

  const fetchAIClients = useCallback(async () => {
    try {
      const response = await fetch('/api/developer/ai-clients/test');
      if (response.ok) {
        const data = await response.json();
        setAiClients(data);
      }
    } catch (error) {
      console.error('Error fetching AI clients:', error);
    }
  }, []);

  const fetchSystemHealth = useCallback(async () => {
    try {
      const response = await fetch('/api/developer/system/health');
      if (response.ok) {
        const data = await response.json();
        setSystemHealth(data);
      }
    } catch (error) {
      console.error('Error fetching system health:', error);
    }
  }, []);

  const fetchStructuredData = useCallback(async () => {
    if (!activeRunId) return;
    try {
      const response = await fetch(`/api/developer/${activeRunId}/structured-data`);
      if (response.ok) {
        const data = await response.json();
        setStructuredData(data);
      }
    } catch (error) {
      console.error('Error fetching structured data:', error);
    }
  }, [activeRunId]);

  const refreshData = useCallback(async () => {
    setIsLoading(true);
    try {
      await Promise.all([
        fetchLogs(),
        fetchMetrics(),
        fetchAIClients(),
        fetchSystemHealth(),
        fetchStructuredData()
      ]);
    } finally {
      setIsLoading(false);
    }
  }, [fetchLogs, fetchMetrics, fetchAIClients, fetchSystemHealth, fetchStructuredData]);

  // Auto refresh every 5 seconds
  useEffect(() => {
    if (autoRefresh) {
      const interval = setInterval(refreshData, 5000);
      return () => clearInterval(interval);
    }
  }, [autoRefresh, refreshData]);

  // Initial load
  useEffect(() => {
    refreshData();
  }, [refreshData]);

  const getStatusColor = (status: boolean) => {
    return status ? '#28a745' : '#dc3545';
  };

  const getLogLevelColor = (level: string | null | undefined) => {
    const normalized = (level || "info").toString().toLowerCase();
    switch (normalized) {
      case 'error': return '#dc3545';
      case 'warning': return '#ffc107';
      case 'info': return '#17a2b8';
      case 'debug': return '#6c757d';
      default: return '#000';
    }
  };

  return (
    <div className="panel developer-tools" style={{ fontFamily: 'monospace' }}>
      <h2>🔧 Developer Tools</h2>

      {!activeRunId && (
        <div style={{
          backgroundColor: '#fff3cd',
          border: '1px solid #ffeaa7',
          padding: 12,
          borderRadius: 4,
          marginBottom: 16,
          color: '#856404'
        }}>
          <strong>Notice:</strong> No active pipeline run. Start a pipeline to see live debugging data.
        </div>
      )}

      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 16, flexWrap: 'wrap' }}>
        <button
          onClick={refreshData}
          disabled={isLoading}
          style={{
            backgroundColor: isLoading ? '#e9ecef' : '#007bff',
            color: isLoading ? '#6c757d' : 'white',
            border: 'none',
            padding: '8px 16px',
            borderRadius: '4px',
            cursor: isLoading ? 'not-allowed' : 'pointer'
          }}
        >
          {isLoading ? '🔄 Refreshing...' : '🔄 Refresh'}
        </button>
        <label style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: '0.9em' }}>
          <input
            type="checkbox"
            checked={autoRefresh}
            onChange={(e) => setAutoRefresh(e.target.checked)}
          />
          Auto-refresh (5s)
        </label>
        {activeRunId && (
          <span style={{
            color: '#666',
            fontSize: '0.85em',
            backgroundColor: '#f8f9fa',
            padding: '4px 8px',
            borderRadius: '3px',
            border: '1px solid #dee2e6'
          }}>
            Run ID: {activeRunId}
          </span>
        )}
      </div>

      <div style={{ marginBottom: 16 }}>
        {(['logs', 'metrics', 'ai-status', 'health', 'data'] as const).map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            style={{
              marginRight: 8,
              backgroundColor: activeTab === tab ? '#007bff' : '#f8f9fa',
              color: activeTab === tab ? 'white' : '#495057',
              border: '1px solid #dee2e6',
              padding: '8px 16px',
              borderRadius: '4px',
              cursor: 'pointer'
            }}
          >
            {tab.charAt(0).toUpperCase() + tab.slice(1).replace('-', ' ')}
          </button>
        ))}
      </div>

      <div style={{ border: '1px solid #dee2e6', borderRadius: '4px', padding: 16, minHeight: '400px' }}>
        {activeTab === 'logs' && (
          <div>
            <h4>Pipeline Logs ({logs.length})</h4>
            <div style={{ maxHeight: '350px', overflowY: 'auto', fontSize: '0.85em' }}>
              {logs.map((log, i) => (
                <div key={i} style={{
                  marginBottom: 8,
                  padding: 8,
                  backgroundColor: '#f8f9fa',
                  borderRadius: '3px',
                  borderLeft: `3px solid ${getLogLevelColor(log.level)}`
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                    <span style={{ fontWeight: 'bold', color: getLogLevelColor(log.level) }}>
                      [{(log.level || 'INFO').toUpperCase()}]
                    </span>
                    <span style={{ color: '#666', fontSize: '0.8em' }}>
                      {log.timestamp ? new Date(log.timestamp).toLocaleTimeString() : '—'}
                    </span>
                  </div>
                  <div><strong>{log.stage || 'pipeline'}</strong>{log.component ? ` - ${log.component}` : ''}</div>
                  <div>{log.message}</div>
                  {log.metadata && (
                    <details style={{ marginTop: 4 }}>
                      <summary style={{ cursor: 'pointer', color: '#007bff' }}>Metadata</summary>
                      <pre style={{ fontSize: '0.75em', backgroundColor: '#e9ecef', padding: 4, marginTop: 4 }}>
                        {JSON.stringify(log.metadata, null, 2)}
                      </pre>
                    </details>
                  )}
                </div>
              ))}
              {logs.length === 0 && <p style={{ color: '#666' }}>No logs available</p>}
            </div>
          </div>
        )}

        {activeTab === 'metrics' && (
          <div>
            <h4>Performance Metrics ({metrics.length})</h4>
            <div style={{ maxHeight: '350px', overflowY: 'auto' }}>
              {metrics.map((metric, i) => (
                <div key={i} style={{
                  marginBottom: 8,
                  padding: 8,
                  backgroundColor: '#f8f9fa',
                  borderRadius: '3px'
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <strong>{metric.stage} - {metric.metric_name}</strong>
                    <span style={{ color: '#666', fontSize: '0.9em' }}>
                      {new Date(metric.recorded_at).toLocaleTimeString()}
                    </span>
                  </div>
                  <div style={{ fontSize: '1.2em', color: '#007bff' }}>
                    {metric.metric_value} {metric.metric_unit}
                  </div>
                </div>
              ))}
              {metrics.length === 0 && <p style={{ color: '#666' }}>No metrics available</p>}
            </div>
          </div>
        )}

        {activeTab === 'ai-status' && (
          <div>
            <h4>AI Client Status</h4>
            {aiClients ? (
              <div style={{ display: 'grid', gap: 12 }}>
                {Object.entries(aiClients).map(([client, status]) => (
                  <div key={client} style={{
                    padding: 12,
                    backgroundColor: '#f8f9fa',
                    borderRadius: '4px',
                    borderLeft: `4px solid ${getStatusColor(status.configured && status.available)}`
                  }}>
                    <h5 style={{ margin: '0 0 8px 0' }}>{client.replace('_', ' ').toUpperCase()}</h5>
                    <div style={{ display: 'flex', gap: 16 }}>
                      <span>
                        Configured: <span style={{ color: getStatusColor(status.configured) }}>
                          {status.configured ? '✓' : '✗'}
                        </span>
                      </span>
                      <span>
                        Available: <span style={{ color: getStatusColor(status.available) }}>
                          {status.available ? '✓' : '✗'}
                        </span>
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p style={{ color: '#666' }}>Loading AI client status...</p>
            )}
          </div>
        )}

        {activeTab === 'health' && (
          <div>
            <h4>System Health</h4>
            {systemHealth ? (
              <div>
                <div style={{
                  padding: 12,
                  backgroundColor: systemHealth.status === 'healthy' ? '#d4edda' : '#fff3cd',
                  borderRadius: '4px',
                  marginBottom: 16
                }}>
                  <h5 style={{ margin: 0 }}>
                    Overall Status: <span style={{
                      color: systemHealth.status === 'healthy' ? '#155724' : '#856404'
                    }}>
                      {systemHealth.status.toUpperCase()}
                    </span>
                  </h5>
                </div>
                <div style={{ display: 'grid', gap: 8 }}>
                  <div>Database: <span style={{ color: getStatusColor(systemHealth.database) }}>
                    {systemHealth.database ? '✓ OK' : '✗ Failed'}
                  </span></div>
                  <div>Storage: <span style={{ color: getStatusColor(systemHealth.storage) }}>
                    {systemHealth.storage ? '✓ OK' : '✗ Failed'}
                  </span></div>
                  <div>WebSockets: <span style={{ color: getStatusColor(systemHealth.websockets) }}>
                    {systemHealth.websockets ? '✓ OK' : '✗ Failed'}
                  </span></div>
                </div>
              </div>
            ) : (
              <p style={{ color: '#666' }}>Loading system health...</p>
            )}
          </div>
        )}

        {activeTab === 'data' && (
          <div>
            <h4>Structured Data</h4>
            {structuredData ? (
              <div>
                <div style={{ marginBottom: 16, fontSize: '0.9em', color: '#666' }}>
                  Size: {structuredData.size} characters | Keys: {structuredData.keys?.join(', ')}
                </div>
                <div style={{ maxHeight: '300px', overflowY: 'auto' }}>
                  <pre style={{
                    backgroundColor: '#f8f9fa',
                    padding: 12,
                    borderRadius: '4px',
                    fontSize: '0.75em',
                    whiteSpace: 'pre-wrap'
                  }}>
                    {JSON.stringify(structuredData.data, null, 2)}
                  </pre>
                </div>
              </div>
            ) : (
              <p style={{ color: '#666' }}>Loading structured data...</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default DeveloperToolsPanel;
