import { BrowserRouter, Routes, Route, Navigate, Link, useLocation } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";
import DashboardPage from "./pages/DashboardPage";
import CreateTaskPage from "./pages/CreateTaskPage";
import TaskDetailPage from "./pages/TaskDetailPage";
import "./styles/design.css";

function AppHeader() {
  const { user, logout } = useAuth();
  const location = useLocation();
  if (!user) return null;

  const isActive = (path: string) => location.pathname === path ? "active" : "";

  return (
    <header className="app-header">
      <Link to="/dashboard" className="logo">Vid<span>Flow</span></Link>
      <nav>
        <Link to="/dashboard" className={isActive("/dashboard")}>Dashboard</Link>
        <Link to="/tasks/new" className={isActive("/tasks/new")}>New Video</Link>
        <button onClick={logout} className="btn btn-ghost btn-sm">Logout</button>
      </nav>
    </header>
  );
}

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <AppShell />
      </BrowserRouter>
    </AuthProvider>
  );
}

function AppShell() {
  const { user } = useAuth();
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
          <Route path="*" element={<Navigate to="/dashboard" />} />
        </Routes>
      </main>
    </div>
  );
}

export default App;
