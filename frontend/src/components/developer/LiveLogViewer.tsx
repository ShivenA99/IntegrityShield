import React from "react";

import type { LogEntry } from "@services/types/developer";

interface LiveLogViewerProps {
  logs: LogEntry[];
  isStreaming: boolean;
}

const LiveLogViewer: React.FC<LiveLogViewerProps> = ({ logs, isStreaming }) => (
  <div className="live-log-viewer">
    <header>
      <h3>Live Logs</h3>
      <span className={isStreaming ? "status streaming" : "status offline"}>
        {isStreaming ? "Streaming" : "Offline"}
      </span>
    </header>
    <ul>
      {logs.map((log, index) => (
        <li key={`${log.timestamp}-${index}`}>
          <span className={`level ${log.level.toLowerCase()}`}>{log.level}</span>
          <span className="stage">[{log.stage}]</span>
          <span className="message">{log.message}</span>
        </li>
      ))}
      {logs.length === 0 ? <li>No log events yet.</li> : null}
    </ul>
  </div>
);

export default LiveLogViewer;
