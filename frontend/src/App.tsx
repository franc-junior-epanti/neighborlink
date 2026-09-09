import { useEffect, useState } from "react";
import { fetchSession, type Session } from "./api/session";
import { SignIn } from "./auth/SignIn";
import { useAuth } from "./auth/AuthContext";
import { ImportVolunteers } from "./ImportVolunteers";

export function App() {
  const { ready, authenticated, username, getAccessToken, signOut } = useAuth();
  const [session, setSession] = useState<Session | null>(null);
  const [activeOrganizationId, setActiveOrganizationId] = useState("");
  const [sessionError, setSessionError] = useState("");

  useEffect(() => {
    if (!authenticated) {
      setSession(null);
      setActiveOrganizationId("");
      return;
    }
    getAccessToken()
      .then(fetchSession)
      .then((result) => {
        setSession(result);
        setActiveOrganizationId(result.organizations[0]?.id ?? "");
      })
      .catch((reason) =>
        setSessionError(reason instanceof Error ? reason.message : "Session indisponible"),
      );
  }, [authenticated, getAccessToken]);

  if (!ready) return <main className="shell">Chargement de la session…</main>;
  if (!authenticated) return <SignIn />;

  return (
    <main className="shell">
      <p className="eyebrow">NeighborLink</p>
      <h1>Coordinate people. Strengthen communities.</h1>
      <p>
        Le socle frontend est prêt. Le tableau de bord communautaire sera construit ici.
      </p>
      <span className="status">Frontend opérationnel</span>
      <p>Session : {username}</p>
      {sessionError && <p role="alert">{sessionError}</p>}
      {session && session.organizations.length > 0 && (
        <label className="organization-picker">
          Association active
          <select
            value={activeOrganizationId}
            onChange={(event) => {
              setActiveOrganizationId(event.target.value);
              setSessionError("");
            }}
          >
            {session.organizations.map((organization) => (
              <option key={organization.id} value={organization.id}>
                {organization.name}
              </option>
            ))}
          </select>
        </label>
      )}
      {session && session.organizations.length === 0 && (
        <p role="status">Aucune association accessible.</p>
      )}
      {activeOrganizationId && (
        <ImportVolunteers
          organizationId={activeOrganizationId}
          getAccessToken={getAccessToken}
        />
      )}
      <button type="button" onClick={() => void signOut()}>
        Se déconnecter
      </button>
    </main>
  );
}
