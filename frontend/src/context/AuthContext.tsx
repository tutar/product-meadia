import { createContext, useContext, useState, type ReactNode } from "react";
import api from "../api/client";

interface User {
  id: string;
  email: string;
  role: string;
}

interface AuthCtx {
  user: User | null;
  login: (email: string, password: string) => Promise<void>;
  loginWithGoogle: (code: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthCtx>(null!);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);

  const login = async (email: string, password: string) => {
    const { data } = await api.post("/auth/token", { grant_type: "password", email, password });
    localStorage.setItem("access_token", data.access_token);
    localStorage.setItem("refresh_token", data.refresh_token);
    const me = await api.get("/auth/me");
    setUser(me.data);
  };

  const loginWithGoogle = async (code: string) => {
    const { data } = await api.post("/auth/token", {
      grant_type: "google_oauth",
      google_code: code,
      redirect_uri: window.location.origin + "/auth/google/callback",
    });
    localStorage.setItem("access_token", data.access_token);
    localStorage.setItem("refresh_token", data.refresh_token);
    const me = await api.get("/auth/me");
    setUser(me.data);
  };

  const register = async (email: string, password: string) => {
    await api.post("/auth/register", { email, password });
  };

  const logout = () => {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, login, loginWithGoogle, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
