import React from "react";

import { useNotifications } from "@contexts/NotificationContext";

const NotificationSystem: React.FC = () => {
  const { toasts, dismiss } = useNotifications();

  return (
    <div className="notification-system">
      {toasts.map((toast) => (
        <div key={toast.id} className={`toast ${toast.intent}`}>
          <strong>{toast.title}</strong>
          {toast.description ? <p>{toast.description}</p> : null}
          <button onClick={() => dismiss(toast.id)}>Dismiss</button>
        </div>
      ))}
    </div>
  );
};

export default NotificationSystem;
