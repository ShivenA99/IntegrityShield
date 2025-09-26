import { useCallback, useEffect, useState } from "react";

export function useLocalStorage<T>(key: string, initialValue: T) {
  const [value, setValue] = useState<T>(() => {
    try {
      const stored = window.localStorage.getItem(key);
      return stored ? (JSON.parse(stored) as T) : initialValue;
    } catch (error) {
      console.warn("Failed to read localStorage", error);
      return initialValue;
    }
  });

  useEffect(() => {
    try {
      window.localStorage.setItem(key, JSON.stringify(value));
    } catch (error) {
      console.warn("Failed to store localStorage", error);
    }
  }, [key, value]);

  const update = useCallback((updater: T | ((current: T) => T)) => {
    setValue((current) => (typeof updater === "function" ? (updater as (c: T) => T)(current) : updater));
  }, []);

  return [value, update] as const;
}
