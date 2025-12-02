import React, { createContext, useCallback, useContext, useMemo, useState } from "react";

interface DeveloperContextValue {
  isDeveloperMode: boolean;
  toggleDeveloperMode: () => void;
}

const DeveloperContext = createContext<DeveloperContextValue | undefined>(undefined);

export const DeveloperProvider: React.FC<React.PropsWithChildren> = ({ children }) => {
  const [isDeveloperMode, setDeveloperMode] = useState<boolean>(() => {
    try {
      return window.localStorage.getItem("fairtestai.developerMode") === "true";
    } catch {
      return false;
    }
  });

  const toggleDeveloperMode = useCallback(() => {
    setDeveloperMode((current) => {
      const next = !current;
      try {
        window.localStorage.setItem("fairtestai.developerMode", String(next));
      } catch (error) {
        console.warn("Failed to persist developer mode", error);
      }
      return next;
    });
  }, []);

  const value = useMemo(
    () => ({
      isDeveloperMode,
      toggleDeveloperMode,
    }),
    [isDeveloperMode, toggleDeveloperMode]
  );

  return <DeveloperContext.Provider value={value}>{children}</DeveloperContext.Provider>;
};

export function useDeveloperContext(): DeveloperContextValue {
  const ctx = useContext(DeveloperContext);
  if (!ctx) {
    throw new Error("useDeveloperContext must be used within a DeveloperProvider");
  }
  return ctx;
}
