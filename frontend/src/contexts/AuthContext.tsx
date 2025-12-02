import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { apiClient } from "@services/api";

interface UserProfile {
  id: string;
  name: string;
  email: string;
  is_active?: boolean;
}

interface AuthContextValue {
  isAuthenticated: boolean;
  user: UserProfile | null;
  isLoading: boolean;
  login: (payload: { email: string; password: string }) => Promise<void>;
  register: (payload: { email: string; password: string; name?: string }) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export const AuthProvider: React.FC<{ children?: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Check for existing session on mount
  useEffect(() => {
    const token = localStorage.getItem("auth_token");
    if (token) {
      apiClient
        .getCurrentUser()
        .then((response) => {
          setUser(response.user);
        })
        .catch(() => {
          // Token invalid, clear it
          localStorage.removeItem("auth_token");
        })
        .finally(() => {
          setIsLoading(false);
        });
    } else {
      setIsLoading(false);
    }
  }, []);

  const login = useCallback(async (payload: { email: string; password: string }) => {
    try {
      const response = await apiClient.login(payload);
      setUser(response.user);
    } catch (error) {
      throw error;
    }
  }, []);

  const register = useCallback(
    async (payload: { email: string; password: string; name?: string }) => {
      try {
        const response = await apiClient.register(payload);
        setUser(response.user);
      } catch (error) {
        throw error;
      }
    },
    []
  );

  const logout = useCallback(async () => {
    try {
      await apiClient.logout();
    } catch (error) {
      // Even if logout fails, clear local state
      console.error("Logout error:", error);
    } finally {
      setUser(null);
      localStorage.removeItem("auth_token");
    }
  }, []);

  const refreshUser = useCallback(async () => {
    try {
      const response = await apiClient.getCurrentUser();
      setUser(response.user);
    } catch (error) {
      // If refresh fails, user might be logged out
      setUser(null);
      localStorage.removeItem("auth_token");
    }
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      isAuthenticated: Boolean(user),
      user,
      isLoading,
      login,
      register,
      logout,
      refreshUser,
    }),
    [user, isLoading, login, register, logout, refreshUser]
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
