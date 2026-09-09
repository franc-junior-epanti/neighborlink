export type ImportIssue = { row: number; field: string; message: string };
export type ImportRow = {
  row: number;
  display_name: string;
  email: string;
  phone_e164: string;
  skills: string[];
  available: boolean;
  email_consent: boolean;
  whatsapp_consent: boolean;
};
export type ImportPreview = {
  import_id: string;
  rows: ImportRow[];
  errors: ImportIssue[];
  warnings: ImportIssue[];
  can_commit: boolean;
};

const apiUrl = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function authenticatedRequest(path: string, token: string, init: RequestInit = {}) {
  const response = await fetch(`${apiUrl}${path}`, {
    ...init,
    headers: { Authorization: `Bearer ${token}`, ...init.headers },
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { detail?: string };
    throw new Error(body.detail ?? "API NeighborLink indisponible");
  }
  return response;
}

export async function previewCsv(organizationId: string, file: File, token: string) {
  const body = new FormData();
  body.append("file", file);
  const response = await authenticatedRequest(
    `/api/v1/organizations/${organizationId}/imports/volunteers/preview`,
    token,
    { method: "POST", body },
  );
  return response.json() as Promise<ImportPreview>;
}

export async function correctImportRow(
  organizationId: string,
  importId: string,
  row: ImportRow,
  token: string,
) {
  const response = await authenticatedRequest(
    `/api/v1/organizations/${organizationId}/imports/${importId}/rows/${row.row}`,
    token,
    { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(row) },
  );
  return response.json() as Promise<ImportPreview>;
}

export async function commitImport(organizationId: string, importId: string, token: string) {
  const response = await authenticatedRequest(
    `/api/v1/organizations/${organizationId}/imports/${importId}/commit`,
    token,
    { method: "POST" },
  );
  return response.json() as Promise<{ imported: number; updated: number; total_volunteers: number }>;
}

export async function loadDemo(organizationId: string, token: string) {
  const response = await authenticatedRequest(
    `/api/v1/organizations/${organizationId}/demo`,
    token,
    { method: "POST" },
  );
  return response.json() as Promise<{ operation_id: string; volunteers: number; roles: string[] }>;
}
