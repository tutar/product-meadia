import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "../api/client";

export default function DashboardPage() {
  const [tasks, setTasks] = useState<any[]>([]);

  useEffect(() => {
    api.get("/tasks").then((r) => setTasks(r.data.items)).catch(() => {});
  }, []);

  return (
    <div style={{ maxWidth: 800, margin: "40px auto" }}>
      <h1>Dashboard</h1>
      <Link to="/tasks/new"><button>Create New Video</button></Link>
      <table>
        <thead><tr><th>Type</th><th>Status</th><th>Created</th><th></th></tr></thead>
        <tbody>
          {tasks.map((t: any) => (
            <tr key={t.id}>
              <td>{t.type}</td>
              <td>{t.status}</td>
              <td>{new Date(t.created_at).toLocaleString()}</td>
              <td><Link to={`/tasks/${t.id}`}>View</Link></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
