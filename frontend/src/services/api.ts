/**
 * API service for making authenticated requests
 */

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "/api";

export interface ApiError {
  error: string;
  message?: string;
}

export class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl;
  }

  private getToken(): string | null {
    return localStorage.getItem("auth_token");
  }

  private setToken(token: string | null): void {
    if (token) {
      localStorage.setItem("auth_token", token);
    } else {
      localStorage.removeItem("auth_token");
    }
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const token = this.getToken();
    const headers: HeadersInit = {
      "Content-Type": "application/json",
      ...options.headers,
    };

    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    const response = await fetch(`${this.baseUrl}${endpoint}`, {
      ...options,
      headers,
    });

    if (!response.ok) {
      const error: ApiError = await response.json().catch(() => ({
        error: `HTTP ${response.status}: ${response.statusText}`,
      }));
      throw new Error(error.error || error.message || "Request failed");
    }

    return response.json();
  }

  // Auth endpoints
  async register(data: {
    email: string;
    password: string;
    name?: string;
  }): Promise<{ token: string; user: any }> {
    const result = await this.request<{ token: string; user: any }>(
      "/auth/register",
      {
        method: "POST",
        body: JSON.stringify(data),
      }
    );
    this.setToken(result.token);
    return result;
  }

  async login(data: { email: string; password: string }): Promise<{
    token: string;
    user: any;
  }> {
    const result = await this.request<{ token: string; user: any }>(
      "/auth/login",
      {
        method: "POST",
        body: JSON.stringify(data),
      }
    );
    this.setToken(result.token);
    return result;
  }

  async logout(): Promise<void> {
    await this.request("/auth/logout", { method: "POST" });
    this.setToken(null);
  }

  async getCurrentUser(): Promise<any> {
    return this.request("/auth/me");
  }

  // API Key endpoints
  async getApiKeys(): Promise<{ api_keys: any[] }> {
    return this.request("/auth/api-keys");
  }

  async saveApiKey(provider: string, apiKey: string): Promise<any> {
    return this.request("/auth/api-keys", {
      method: "POST",
      body: JSON.stringify({ provider, api_key: apiKey }),
    });
  }

  async deleteApiKey(provider: string): Promise<void> {
    return this.request(`/auth/api-keys/${provider}`, {
      method: "DELETE",
    });
  }

  async validateApiKey(provider: string, apiKey: string): Promise<{
    valid: boolean;
    message?: string;
  }> {
    return this.request(`/auth/api-keys/${provider}/validate`, {
      method: "POST",
      body: JSON.stringify({ api_key: apiKey }),
    });
  }
}

export const apiClient = new ApiClient();

