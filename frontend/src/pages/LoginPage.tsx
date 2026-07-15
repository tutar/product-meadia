import { useState, useEffect, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../context/AuthContext";
import { useNavigate, Link, useSearchParams } from "react-router-dom";

const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID || "";

function googleAuthUrl(): string {
  const redirect = window.location.origin + "/login";
  return `https://accounts.google.com/o/oauth2/v2/auth?client_id=${GOOGLE_CLIENT_ID}&redirect_uri=${encodeURIComponent(redirect)}&response_type=code&scope=email+profile&prompt=select_account`;
}

export default function LoginPage() {
  const { t } = useTranslation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const { login, loginWithGoogle } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  useEffect(() => {
    const code = searchParams.get("code");
    if (code) {
      setLoading(true);
      loginWithGoogle(code)
        .then(() => navigate("/dashboard"))
        .catch(() => setError(t("auth.googleFailed")))
        .finally(() => setLoading(false));
    }
  }, [searchParams]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(email, password);
      navigate("/dashboard");
    } catch (err: any) {
      setError(err?.response?.data?.detail || t("auth.invalidCredentials"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-card card">
        <h1>{t("auth.signInTo")} <span style={{ color: "var(--accent)" }}>{t("app.title")}</span></h1>
        <p className="subtitle">{t("app.subtitle")}</p>

        {error && (
          <div style={{ background: "rgba(248,113,113,0.1)", color: "var(--danger)", padding: "10px 14px", borderRadius: "var(--radius)", marginBottom: 20, fontSize: "0.85rem" }}>
            {error}
          </div>
        )}

        {GOOGLE_CLIENT_ID && (
          <a href={googleAuthUrl()} className="btn btn-secondary btn-lg" style={{ width: "100%", marginBottom: 24, textDecoration: "none" }}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none"><path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4"/><path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/><path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/><path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/></svg>
            {t("auth.continueWithGoogle")}
          </a>
        )}

        {GOOGLE_CLIENT_ID && (
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 24, color: "var(--text-muted)", fontSize: "0.8rem" }}>
            <div style={{ flex: 1, height: 1, background: "var(--border)" }} />
            {t("auth.orWithEmail")}
            <div style={{ flex: 1, height: 1, background: "var(--border)" }} />
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label className="form-label">{t("auth.email")}</label>
            <input className="input" type="email" placeholder={t("auth.emailPlaceholder")} value={email} onChange={e => setEmail(e.target.value)} required />
          </div>
          <div className="form-group">
            <label className="form-label">{t("auth.password")}</label>
            <input className="input" type="password" placeholder="••••••••" value={password} onChange={e => setPassword(e.target.value)} required />
          </div>
          <div className="form-actions">
            <button className="btn btn-primary btn-lg" style={{ width: "100%" }} type="submit" disabled={loading}>
              {loading ? t("auth.signingIn") : t("auth.signInButton")}
            </button>
          </div>
        </form>

        <p className="form-footer">{t("auth.noAccount")} <Link to="/register">{t("auth.createOne")}</Link></p>
      </div>
    </div>
  );
}
