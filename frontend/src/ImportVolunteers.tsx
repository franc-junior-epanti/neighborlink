import { useState, type ChangeEvent } from "react";
import {
  commitImport,
  correctImportRow,
  loadDemo,
  previewCsv,
  type ImportPreview,
  type ImportRow,
} from "./api/imports";

type Props = { organizationId: string; getAccessToken: () => Promise<string> };

export function ImportVolunteers({ organizationId, getAccessToken }: Props) {
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  async function run(action: (token: string) => Promise<void>) {
    setBusy(true);
    setMessage("");
    try {
      await action(await getAccessToken());
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Action impossible");
    } finally {
      setBusy(false);
    }
  }

  function selectFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    void run(async (token) => setPreview(await previewCsv(organizationId, file, token)));
  }

  function replaceRow(updated: ImportRow) {
    setPreview((current) =>
      current ? { ...current, rows: current.rows.map((row) => (row.row === updated.row ? updated : row)) } : current,
    );
  }

  function saveRow(row: ImportRow) {
    if (!preview) return;
    void run(async (token) =>
      setPreview(await correctImportRow(organizationId, preview.import_id, row, token)),
    );
  }

  return (
    <section className="import-card">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Données de démonstration</p>
          <h2>Préparer les bénévoles</h2>
          <p>Prévisualisez et corrigez le CSV avant toute écriture dans PostgreSQL.</p>
        </div>
        <button
          type="button"
          disabled={busy}
          onClick={() => void run(async (token) => {
            const result = await loadDemo(organizationId, token);
            setMessage(`${result.volunteers} bénévoles et ${result.roles.length} rôles sont prêts.`);
          })}
        >
          Charger le scénario Douala
        </button>
      </div>
      <label className="file-picker">
        Importer un CSV
        <input type="file" accept=".csv,text/csv" disabled={busy} onChange={selectFile} />
      </label>
      {message && <p role="status" className="notice">{message}</p>}
      {preview && (
        <>
          <div className="summary">
            <strong>{preview.rows.length} lignes</strong>
            <span>{preview.errors.length} erreurs</span>
            <span>{preview.warnings.length} avertissements</span>
            <span>Aucune donnée enregistrée</span>
          </div>
          {preview.errors.map((issue) => (
            <p className="error" key={`${issue.row}-${issue.field}`}>
              Ligne {issue.row}, {issue.field} : {issue.message}
            </p>
          ))}
          <div className="preview-table">
            {preview.rows.map((row) => (
              <div className="preview-row" key={row.row}>
                <span>Ligne {row.row}</span>
                <input
                  aria-label={`Nom ligne ${row.row}`}
                  value={row.display_name}
                  onChange={(event) => replaceRow({ ...row, display_name: event.target.value })}
                />
                <input
                  aria-label={`Courriel ligne ${row.row}`}
                  value={row.email}
                  onChange={(event) => replaceRow({ ...row, email: event.target.value })}
                />
                <input
                  aria-label={`Compétences ligne ${row.row}`}
                  value={row.skills.join(" | ")}
                  onChange={(event) => replaceRow({
                    ...row,
                    skills: event.target.value.split("|").map((value) => value.trim()).filter(Boolean),
                  })}
                />
                <button type="button" disabled={busy} onClick={() => saveRow(row)}>Valider la ligne</button>
              </div>
            ))}
          </div>
          <button
            type="button"
            disabled={busy || !preview.can_commit}
            onClick={() => void run(async (token) => {
              const result = await commitImport(organizationId, preview.import_id, token);
              setPreview(null);
              setMessage(`Import confirmé : ${result.imported} ajoutés, ${result.updated} actualisés.`);
            })}
          >
            Confirmer l’import
          </button>
        </>
      )}
    </section>
  );
}
