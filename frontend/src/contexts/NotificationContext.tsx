import React, { createContext, useCallback, useContext, useMemo, useState } from "react";

export interface ToastMessage {
  id: string;
  title: string;
  description?: string;
  intent?: "info" | "success" | "warning" | "error";
  timeout?: number;
}

interface NotificationContextValue {
  toasts: ToastMessage[];
  push: (toast: Omit<ToastMessage, "id">) => void;
  dismiss: (id: string) => void;
}

const NotificationContext = createContext<NotificationContextValue | undefined>(undefined);

export const NotificationProvider: React.FC<React.PropsWithChildren> = ({ children }) => {
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  const push = useCallback((toast: Omit<ToastMessage, "id">) => {
    const id = crypto.randomUUID();
    const entry: ToastMessage = { id, intent: "info", timeout: 6000, ...toast };
    setToasts((current) => [...current, entry]);

    if (entry.timeout) {
      window.setTimeout(() => {
        setToasts((current) => current.filter((item) => item.id !== id));
      }, entry.timeout);
    }
  }, []);

  const dismiss = useCallback((id: string) => {
    setToasts((current) => current.filter((item) => item.id !== id));
  }, []);

  const value = useMemo(() => ({ toasts, push, dismiss }), [toasts, push, dismiss]);

  return <NotificationContext.Provider value={value}>{children}</NotificationContext.Provider>;
};

export function useNotifications(): NotificationContextValue {
  const ctx = useContext(NotificationContext);
  if (!ctx) {
    throw new Error("useNotifications must be used within a NotificationProvider");
  }
  return ctx;
}
