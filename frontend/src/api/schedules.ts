export type Operation = {
  id: string;
  name: string;
  event_date: string;
  location_name: string;
  status: string;
};

export type VersionSummary = {
  id: string;
  revision: number;
  status: string;
  origin: string;
  total_score: number;
  created_at: string;
};

export type Assignment = {
  id: string;
  volunteer_id: string;
  volunteer_name: string;
  shift_id: string;
  shift_name: string;
  starts_at: string;
  ends_at: string;
  response_status: string;
  reason_codes: string[];
  distance_km: number | null;
};

export type Shift = {
  id: string;
  name: string;
  role_name: string;
  starts_at: string;
  ends_at: string;
  capacity: number;
};

export type ToolCall = {
  tool: string;
  status: string;
  timestamp: string;
};

export type VersionDetail = VersionSummary & {
  operation_id: string;
  score_details: Record<string, number>;
  conflicts: string[];
  explanations: string[];
  assignments: Assignment[];
  shifts: Shift[];
  agent_session_id: string | null;
  agent_request_id: string | null;
  tool_calls: ToolCall[];
};

export type VersionDiff = {
  base_version_id: string | null;
  target_version_id: string;
  added: string[];
  removed: string[];
};

const apiUrl = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function request(path: string, token: string, init: RequestInit = {}) {
  const response = await fetch(`${apiUrl}${path}`, {
    ...init,
    headers: { Authorization: `Bearer ${token}`, ...init.headers },
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { detail?: string };
    throw new Error(body.detail ?? "Action planning impossible");
  }
  return response;
}

export async function fetchOperations(organizationId: string, token: string) {
  return (await request(`/api/v1/organizations/${organizationId}/operations`, token)).json() as Promise<Operation[]>;
}

export async function fetchVersions(operationId: string, token: string) {
  return (await request(`/api/v1/operations/${operationId}/schedule-versions`, token)).json() as Promise<VersionSummary[]>;
}

export async function fetchVersion(operationId: string, versionId: string, token: string) {
  return (await request(`/api/v1/operations/${operationId}/schedule-versions/${versionId}`, token)).json() as Promise<VersionDetail>;
}

export async function generateVersion(operationId: string, instruction: string, token: string) {
  return (await request(`/api/v1/operations/${operationId}/schedule-versions`, token, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ instruction: instruction.trim() || null }),
  })).json() as Promise<VersionDetail>;
}

export async function moveVolunteer(
  versionId: string,
  volunteerId: string,
  fromShiftId: string,
  toShiftId: string,
  token: string,
) {
  return (await request(`/api/v1/schedule-versions/${versionId}/manual-moves`, token, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      volunteer_id: volunteerId,
      from_shift_id: fromShiftId,
      to_shift_id: toShiftId,
    }),
  })).json() as Promise<VersionDetail>;
}

export async function fetchDiff(versionId: string, token: string) {
  return (await request(`/api/v1/schedule-versions/${versionId}/diff`, token)).json() as Promise<VersionDiff>;
}
