import { useEffect, useRef, useState } from "react";
import { BrowserRouter, Routes, Route, Navigate, Link, useLocation } from "react-router-dom";
import { useTranslation, I18nextProvider } from "react-i18next";
import i18n from "./i18n";
import { AuthProvider, useAuth } from "./context/AuthContext";
import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";
import DashboardPage from "./pages/DashboardPage";
import CreateTaskPage from "./pages/CreateTaskPage";
import TaskDetailPage from "./pages/TaskDetailPage";
import CategoriesPage from "./pages/CategoriesPage";
import ProductsPage from "./pages/ProductsPage";
import ProductFormPage from "./pages/ProductFormPage";
import "./styles/design.css";

type Theme = "studio" | "work";

function ThemeBootstrap() {
  useEffect(() => {
    document.documentElement.dataset.theme = localStorage.getItem("productmedia-theme") === "work" ? "work" : "studio";
  }, []);
  return null;
}

function avatarColor(identity: string) {
  const hash = Array.from(identity).reduce((value, character) =>
    ((value << 5) - value + character.codePointAt(0)!) | 0, 0);
  return `hsl(${Math.abs(hash) % 360} 48% 42%)`;
}

function AppHeader() {
  const { user, logout } = useAuth();
  const { t, i18n } = useTranslation();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const [theme, setTheme] = useState<Theme>(() =>
    localStorage.getItem("productmedia-theme") === "work" ? "work" : "studio",
  );
  const profileMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("productmedia-theme", theme);
  }, [theme]);

  useEffect(() => {
    if (!menuOpen) return;
    const closeOnOutsideClick = (event: MouseEvent) => {
      if (!profileMenuRef.current?.contains(event.target as Node)) setMenuOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMenuOpen(false);
    };
    document.addEventListener("mousedown", closeOnOutsideClick);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeOnOutsideClick);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [menuOpen]);

  if (!user) return null;

  const isActive = (path: string) => location.pathname === path ? "active" : "";
  const userName = user.email.split("@")[0] || user.email;
  const initial = Array.from(userName)[0]?.toLocaleUpperCase() || "P";
  const nextTheme = theme === "studio" ? "work" : "studio";
  const changeTheme = () => setTheme(nextTheme);
  const changeLanguage = () => {
    i18n.changeLanguage(i18n.language === "zh" ? "en" : "zh");
    setMenuOpen(false);
  };

  return (
    <header className="app-header">
      <Link to="/dashboard" className="logo">Product<span>Media</span></Link>
      <nav>
        <Link to="/dashboard" className={isActive("/dashboard")}>{t("nav.dashboard")}</Link>
        <Link to="/tasks/new" className={isActive("/tasks/new")}>{t("nav.newVideo")}</Link>
        <Link to="/categories" className={isActive("/categories")}>{t("nav.categories")}</Link>
        <Link to="/products" className={isActive("/products")}>{t("nav.products")}</Link>
        <div className="profile-menu" ref={profileMenuRef}>
          <button
            type="button"
            className="avatar-button"
            onClick={() => setMenuOpen(open => !open)}
            aria-label={t(menuOpen ? "profile.closeMenu" : "profile.openMenu")}
            aria-expanded={menuOpen}
            aria-haspopup="menu"
          >
            <span className="avatar" style={{ backgroundColor: avatarColor(user.email) }}>{initial}</span>
            <span className="avatar-chevron" aria-hidden="true">⌄</span>
          </button>
          {menuOpen && (
            <div className="profile-dropdown" role="menu">
              <div className="profile-identity">
                <span className="avatar avatar-lg" style={{ backgroundColor: avatarColor(user.email) }}>{initial}</span>
                <span>
                  <strong>{userName}</strong>
                  <small>{user.email}</small>
                </span>
              </div>
              <div className="profile-menu-divider" />
              <button type="button" className="profile-menu-item" onClick={changeTheme} role="menuitem">
                <span>{t("profile.appearance")}</span>
                <span className="profile-menu-value">{theme === "studio" ? "☾" : "☀"} {t(`theme.${theme}`)}</span>
              </button>
              <button type="button" className="profile-menu-item" onClick={changeLanguage} role="menuitem">
                <span>{t("profile.language")}</span>
                <span className="profile-menu-value">{i18n.language === "zh" ? "中文" : "English"}</span>
              </button>
              <div className="profile-menu-divider" />
              <button type="button" className="profile-menu-item profile-menu-danger" onClick={logout} role="menuitem">
                {t("nav.logout")}
              </button>
            </div>
          )}
        </div>
      </nav>
    </header>
  );
}

function App() {
  return (
    <I18nextProvider i18n={i18n}>
      <ThemeBootstrap />
      <AuthProvider>
        <BrowserRouter>
          <AppShell />
        </BrowserRouter>
      </AuthProvider>
    </I18nextProvider>
  );
}

function AppShell() {
  const { user, loading } = useAuth();
  if (loading) return null;
  if (!user) {
    return (
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="*" element={<Navigate to="/login" />} />
      </Routes>
    );
  }

  return (
    <div className="app-shell">
      <AppHeader />
      <main className="app-main">
        <Routes>
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/tasks/new" element={<CreateTaskPage />} />
          <Route path="/tasks/:id" element={<TaskDetailPage />} />
          <Route path="/categories" element={<CategoriesPage />} />
          <Route path="/products" element={<ProductsPage />} />
          <Route path="/products/new" element={<ProductFormPage />} />
          <Route path="/products/:id/edit" element={<ProductFormPage />} />
          <Route path="*" element={<Navigate to="/dashboard" />} />
        </Routes>
      </main>
    </div>
  );
}

export default App;
