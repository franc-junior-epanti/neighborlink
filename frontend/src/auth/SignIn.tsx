import { useState, type FormEvent } from "react";
import { authMode } from "./config";
import { useAuth } from "./AuthContext";

export function SignIn() {
  const { signIn } = useAuth();
  const [username, setUsername] = useState("coordinateur@neighborlink.test");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      await signIn(username, password);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Connexion refusée");
    }
  }

  return (
    <main className="shell auth-shell">
      <p className="eyebrow">NeighborLink</p>
      <h1>Bienvenue.</h1>
      <p>Connectez-vous pour coordonner votre association.</p>
      {authMode === "local" && <p className="notice">Mode local — aucune identité AWS utilisée.</p>}
      <form onSubmit={submit} className="auth-form">
        <label>
          Adresse courriel
          <input value={username} onChange={(event) => setUsername(event.target.value)} required />
        </label>
        <label>
          Mot de passe
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required={authMode === "cognito"}
          />
        </label>
        {error && <p role="alert">{error}</p>}
        <button type="submit">Se connecter</button>
      </form>
    </main>
  );
}
