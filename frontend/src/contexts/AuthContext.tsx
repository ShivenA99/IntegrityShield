import React, { createContext, useCallback, useContext, useMemo, useState } from "react";

interface UserProfile {
  id: string;
  name: string;
  email: string;
}

interface AuthContextValue {
  isAuthenticated: boolean;
  user: UserProfile | null;
  login: (payload: { email: string; name?: string }) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export const AuthProvider: React.FC<{ children?: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<UserProfile | null>(null);

  const login = useCallback((payload: { email: string; name?: string }) => {
    const email = payload.email.trim().toLowerCase();
    if (!email) return;
    setUser({
      id: crypto.randomUUID(),
      name: payload.name?.trim() || email.split("@")[0],
      email,
    });
  }, []);

  const logout = useCallback(() => setUser(null), []);

  const value = useMemo<AuthContextValue>(
    () => ({
      isAuthenticated: Boolean(user),
      user,
      login,
      logout,
    }),
    [user, login, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
};
