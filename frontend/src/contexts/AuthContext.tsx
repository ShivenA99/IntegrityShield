import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { apiClient } from "@services/api";

interface UserProfile {
  id: string;
  name: string;
  email?: string; // Optional now
  is_active?: boolean;
  has_openai_key?: boolean;
}

interface AuthContextValue {
  isAuthenticated: boolean;
  user: UserProfile | null;
  isLoading: boolean;
  loginWithKey: (payload: { openai_api_key: string; email?: string }) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
  validateSession: () => Promise<boolean>;
  /** @deprecated Use loginWithKey instead */
  login?: (payload: { email: string; password: string }) => Promise<void>;
  /** @deprecated Use loginWithKey instead */
  register?: (payload: { email: string; password: string; name?: string }) => Promise<void>;
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

  // Periodic session validation (every 5 minutes)
  useEffect(() => {
    if (!user) return;

    const validateInterval = setInterval(async () => {
      const isValid = await validateSession();
      if (!isValid) {
        console.warn("Session expired: OpenAI key is no longer valid");
        // User state already cleared by validateSession
      }
    }, 5 * 60 * 1000); // 5 minutes

    return () => clearInterval(validateInterval);
  }, [user, validateSession]);

  const loginWithKey = useCallback(async (payload: { openai_api_key: string; email?: string }) => {
    try {
      const response = await apiClient.loginWithKey(payload);
      setUser(response.user);
    } catch (error) {
      throw error;
    }
  }, []);

  const validateSession = useCallback(async (): Promise<boolean> => {
    try {
      const response = await apiClient.validateSession();
      if (!response.valid) {
        // Session invalid - clear user state
        setUser(null);
        localStorage.removeItem("auth_token");
        return false;
      }
      // Optionally update user data
      if (response.user) {
        setUser(response.user);
      }
      return true;
    } catch (error) {
      // Validation failed - clear user state
      setUser(null);
      localStorage.removeItem("auth_token");
      return false;
    }
  }, []);

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
      loginWithKey,
      logout,
      refreshUser,
      validateSession,
    }),
    [user, isLoading, loginWithKey, logout, refreshUser, validateSession]
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
