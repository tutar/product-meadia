import { useState, type FormEvent } from "react";
import { useAuth } from "../context/AuthContext";
import { useNavigate, Link } from "react-router-dom";

export default function RegisterPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const { register } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    await register(email, password);
    navigate("/login");
  };

  return (
    <div style={{ maxWidth: 400, margin: "100px auto" }}>
      <h1>Register</h1>
      <form onSubmit={handleSubmit}>
        <div><input type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} required /></div>
        <div><input type="password" placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} required /></div>
        <button type="submit">Register</button>
      </form>
      <p>Already have an account? <Link to="/login">Login</Link></p>
    </div>
  );
}
