export type OrganizationSummary = {
  id: string;
  name: string;
  slug: string;
  role: string;
};

export type Session = {
  user_id: string;
  display_name: string;
  email: string;
  organizations: OrganizationSummary[];
};

const apiUrl = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export async function fetchSession(accessToken: string): Promise<Session> {
  const response = await fetch(`${apiUrl}/api/v1/me`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!response.ok) {
    throw new Error(response.status === 401 ? "Session expirée" : "API NeighborLink indisponible");
  }
  return response.json() as Promise<Session>;
}
