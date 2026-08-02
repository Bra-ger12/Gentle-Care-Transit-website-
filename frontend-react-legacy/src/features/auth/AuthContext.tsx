import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { apiClient, setAccessToken, setOnAuthFailure } from "../../lib/apiClient";

export type Role = "RIDER" | "DRIVER" | "ADMIN";

export interface AuthUser {
  id: string;
  email: string;
  phone_number: string | null;
  first_name: string;
  last_name: string;
  role: Role;
  is_verified: boolean;
}

interface AuthContextValue {
  user: AuthUser | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (identifier: string, password: string) => Promise<AuthUser>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const fetchMe = useCallback(async () => {
    const response = await apiClient.get<AuthUser>("/auth/me/");
    setUser(response.data);
    return response.data;
  }, []);

  const clearSession = useCallback(() => {
    setAccessToken(null);
    setUser(null);
  }, []);

  useEffect(() => {
    setOnAuthFailure(clearSession);
    return () => setOnAuthFailure(null);
  }, [clearSession]);

  useEffect(() => {
    // Silently restore a session on page load from the httpOnly refresh cookie.
    (async () => {
      try {
        const response = await apiClient.post<{ access: string }>(
          "/auth/refresh/",
        );
        setAccessToken(response.data.access);
        await fetchMe();
      } catch {
        clearSession();
      } finally {
        setIsLoading(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const login = useCallback(
    async (identifier: string, password: string) => {
      const response = await apiClient.post<{ access: string }>(
        "/auth/login/",
        { identifier, password },
      );
      setAccessToken(response.data.access);
      return fetchMe();
    },
    [fetchMe],
  );

  const logout = useCallback(async () => {
    try {
      await apiClient.post("/auth/logout/");
    } finally {
      clearSession();
    }
  }, [clearSession]);

  return (
    <AuthContext.Provider
      value={{ user, isAuthenticated: !!user, isLoading, login, logout }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}
