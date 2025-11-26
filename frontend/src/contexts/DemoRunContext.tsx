import React, { createContext, useContext, useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router-dom";

export type DemoRunPreviewType = "image" | "pdf";

export interface DemoRunMetadata {
  runId: string;
  stageLabel?: string;
  statusLabel?: string;
  downloads?: number;
  classrooms?: number;
  document?: {
    filename?: string;
    pages?: number | string | null;
    previewUrl?: string | null;
    previewType?: DemoRunPreviewType;
  };
  answerKey?: {
    filename?: string;
  };
}

interface DemoRunContextValue {
  demoRun: DemoRunMetadata | null;
  setDemoRun: React.Dispatch<React.SetStateAction<DemoRunMetadata | null>>;
}

const DemoRunContext = createContext<DemoRunContextValue | undefined>(undefined);

export const DemoRunProvider: React.FC<{ children?: React.ReactNode }> = ({ children }) => {
  const [demoRun, setDemoRun] = useState<DemoRunMetadata | null>(null);
  const location = useLocation();

  useEffect(() => {
    const allowedPrefixes = ["/demo", "/classrooms"];
    const isAllowed = allowedPrefixes.some((prefix) => location.pathname.startsWith(prefix));
    if (!isAllowed) {
      setDemoRun(null);
    }
  }, [location.pathname]);

  const value = useMemo(() => ({ demoRun, setDemoRun }), [demoRun]);

  return <DemoRunContext.Provider value={value}>{children}</DemoRunContext.Provider>;
};

export const useDemoRun = (): DemoRunContextValue => {
  const context = useContext(DemoRunContext);
  if (!context) {
    throw new Error("useDemoRun must be used within a DemoRunProvider");
  }
  return context;
};
