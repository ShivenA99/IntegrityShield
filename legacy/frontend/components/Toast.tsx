import React, { createContext, useContext, useState, useCallback, useMemo } from 'react';

export type ToastType = 'info' | 'success' | 'error';

type ToastItem = {
  id: number;
  message: string;
  type: ToastType;
};

type ToastContextType = {
  show: (message: string, type?: ToastType) => void;
};

const ToastContext = createContext<ToastContextType | null>(null);

export const useToast = (): ToastContextType => {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used within ToastProvider');
  return ctx;
};

export const ToastProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [items, setItems] = useState<ToastItem[]>([]);
  const show = useCallback((message: string, type: ToastType = 'info') => {
    const id = Date.now() + Math.random();
    setItems((prev) => [...prev, { id, message, type }]);
    setTimeout(() => {
      setItems((prev) => prev.filter((t) => t.id !== id));
    }, 3000);
  }, []);

  const value = useMemo(() => ({ show }), [show]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="fixed top-4 right-4 z-50 space-y-2">
        {items.map((t) => (
          <div key={t.id} className={`px-3 py-2 rounded shadow-lg text-sm border ${t.type === 'success' ? 'bg-emerald-700/90 border-emerald-500' : t.type === 'error' ? 'bg-red-700/90 border-red-500' : 'bg-slate-800/90 border-slate-600'} text-white`}>{t.message}</div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}; 