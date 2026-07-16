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

function LangSwitcher() {
  const { i18n } = useTranslation();
  const toggle = () => i18n.changeLanguage(i18n.language === "zh" ? "en" : "zh");
  return (
    <button onClick={toggle} className="btn btn-ghost btn-sm" style={{ fontSize: "0.8rem", minWidth: 36 }}>
      {i18n.language === "zh" ? "EN" : "中"}
    </button>
  );
}

function AppHeader() {
  const { user, logout } = useAuth();
  const { t } = useTranslation();
  const location = useLocation();
  if (!user) return null;

  const isActive = (path: string) => location.pathname === path ? "active" : "";

  return (
    <header className="app-header">
      <Link to="/dashboard" className="logo">Vid<span>Flow</span></Link>
      <nav>
        <Link to="/dashboard" className={isActive("/dashboard")}>{t("nav.dashboard")}</Link>
        <Link to="/tasks/new" className={isActive("/tasks/new")}>{t("nav.newVideo")}</Link>
        <Link to="/categories" className={isActive("/categories")}>{t("nav.categories")}</Link>
        <Link to="/products" className={isActive("/products")}>{t("nav.products")}</Link>
        <LangSwitcher />
        <button onClick={logout} className="btn btn-ghost btn-sm">{t("nav.logout")}</button>
      </nav>
    </header>
  );
}

function App() {
  return (
    <I18nextProvider i18n={i18n}>
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
