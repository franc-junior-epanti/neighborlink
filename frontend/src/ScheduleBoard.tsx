import { useCallback, useEffect, useState } from "react";
import {
  dispatchNotifications,
  fetchDiff,
  fetchOperations,
  fetchOutboxStatus,
  fetchVersion,
  fetchVersions,
  generateVersion,
  moveVolunteer,
  publishVersion,
  type OutboxStatus,
  type Operation,
  type VersionDetail,
  type VersionDiff,
  type VersionSummary,
} from "./api/schedules";

type Props = {
  organizationId: string;
  preferredOperationId?: string;
  getAccessToken: () => Promise<string>;
};

export function ScheduleBoard({ organizationId, preferredOperationId, getAccessToken }: Props) {
  const [operations, setOperations] = useState<Operation[]>([]);
  const [operationId, setOperationId] = useState("");
  const [versions, setVersions] = useState<VersionSummary[]>([]);
  const [selected, setSelected] = useState<VersionDetail | null>(null);
  const [diff, setDiff] = useState<VersionDiff | null>(null);
  const [instruction, setInstruction] = useState("");
  const [assignmentId, setAssignmentId] = useState("");
  const [targetShiftId, setTargetShiftId] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [outbox, setOutbox] = useState<OutboxStatus[]>([]);

  const loadVersions = useCallback(async (targetOperationId: string, preferredVersionId?: string) => {
    if (!targetOperationId) return;
    const token = await getAccessToken();
    const summaries = await fetchVersions(targetOperationId, token);
    setVersions(summaries);
    const versionId = preferredVersionId ?? summaries[0]?.id;
    if (!versionId) {
      setSelected(null);
      setDiff(null);
      setOutbox([]);
      return;
    }
    const detail = await fetchVersion(targetOperationId, versionId, token);
    setSelected(detail);
    setAssignmentId(detail.assignments[0]?.id ?? "");
    setTargetShiftId(detail.assignments[0]?.shift_id ?? detail.shifts[0]?.id ?? "");
    setDiff(detail.revision > 1 ? await fetchDiff(detail.id, token) : null);
    setOutbox(detail.status === "published" ? await fetchOutboxStatus(detail.id, token) : []);
  }, [getAccessToken]);

  useEffect(() => {
    setMessage("");
    void getAccessToken()
      .then((token) => fetchOperations(organizationId, token))
      .then((items) => {
        setOperations(items);
        const next = preferredOperationId && items.some((item) => item.id === preferredOperationId)
          ? preferredOperationId
          : items[0]?.id ?? "";
        setOperationId(next);
        return loadVersions(next);
      })
      .catch((error) => setMessage(error instanceof Error ? error.message : "Planning indisponible"));
  }, [organizationId, preferredOperationId, getAccessToken, loadVersions]);

  async function run(action: (token: string) => Promise<VersionDetail>) {
    setBusy(true);
    setMessage("");
    try {
      const detail = await action(await getAccessToken());
      await loadVersions(detail.operation_id, detail.id);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Action impossible");
    } finally {
      setBusy(false);
    }
  }

  const assignment = selected?.assignments.find((item) => item.id === assignmentId);

  async function handlePublish() {
    if (!selected) return;
    setBusy(true);
    setMessage("");
    try {
      const token = await getAccessToken();
      const result = await publishVersion(selected.id, selected.revision, token);
      setOutbox(result.notifications);
      await loadVersions(selected.operation_id, selected.id);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Publication impossible");
    } finally {
      setBusy(false);
    }
  }

  async function handleDispatch() {
    if (!selected) return;
    setBusy(true);
    setMessage("");
    try {
      const token = await getAccessToken();
      const result = await dispatchNotifications(selected.id, token);
      setOutbox(result.notifications);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Envoi impossible");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="schedule-card">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Planification vérifiable</p>
          <h2>Versions du planning</h2>
          <p>Chaque génération et déplacement crée un nouveau brouillon indépendant.</p>
        </div>
        <label className="compact-field">
          Opération
          <select value={operationId} onChange={(event) => {
            setOperationId(event.target.value);
            void loadVersions(event.target.value);
          }}>
            {operations.map((operation) => (
              <option key={operation.id} value={operation.id}>{operation.name}</option>
            ))}
          </select>
        </label>
      </div>

      {!operationId && <p className="notice">Chargez d’abord le scénario Douala.</p>}
      {operationId && (
        <div className="agent-command">
          <label>
            Instruction à NeighborLink
            <input
              value={instruction}
              onChange={(event) => setInstruction(event.target.value)}
              placeholder="Ex. privilégie les bénévoles proches"
            />
          </label>
          <button disabled={busy} type="button" onClick={() => void run(
            (token) => generateVersion(operationId, instruction, token),
          )}>Générer un nouveau brouillon</button>
        </div>
      )}
      {message && <p role="alert" className="notice">{message}</p>}

      {versions.length > 0 && (
        <nav className="version-tabs" aria-label="Versions du planning">
          {versions.map((version) => (
            <button
              type="button"
              className={selected?.id === version.id ? "active-version" : "secondary-button"}
              key={version.id}
              onClick={() => void loadVersions(operationId, version.id)}
            >
              V{version.revision} · {version.status} · {version.total_score}
            </button>
          ))}
        </nav>
      )}

      {selected && (
        <div className="schedule-detail">
          <div className="metrics">
            <span><strong>V{selected.revision}</strong> révision</span>
            <span><strong>{selected.total_score}</strong> score</span>
            <span><strong>{selected.assignments.length}</strong> affectations</span>
            <span><strong>{selected.conflicts.length}</strong> conflits</span>
          </div>
          <div className="schedule-grid">
            <div>
              <h3>Affectations</h3>
              {selected.assignments.map((item) => (
                <article className="assignment" key={item.id}>
                  <strong>{item.volunteer_name}</strong>
                  <span>{item.shift_name}</span>
                  <small>{item.reason_codes.join(" · ")}</small>
                </article>
              ))}
            </div>
            <div>
              <h3>Explications</h3>
              {selected.explanations.map((item) => <p key={item}>{item}</p>)}
              {selected.conflicts.map((item) => <p className="error" key={item}>{item}</p>)}
            </div>
          </div>

          {selected.assignments.length > 0 && (
            <div className="manual-move">
              <h3>Déplacement manuel</h3>
              <select aria-label="Bénévole à déplacer" value={assignmentId} onChange={(event) => {
                const next = selected.assignments.find((item) => item.id === event.target.value);
                setAssignmentId(event.target.value);
                setTargetShiftId(next?.shift_id ?? "");
              }}>
                {selected.assignments.map((item) => (
                  <option value={item.id} key={item.id}>{item.volunteer_name} — {item.shift_name}</option>
                ))}
              </select>
              <select aria-label="Nouveau créneau" value={targetShiftId} onChange={(event) => setTargetShiftId(event.target.value)}>
                {selected.shifts.map((shift) => <option value={shift.id} key={shift.id}>{shift.name}</option>)}
              </select>
              <button disabled={busy || !assignment || !targetShiftId} type="button" onClick={() => {
                if (!assignment) return;
                void run((token) => moveVolunteer(
                  selected.id,
                  assignment.volunteer_id,
                  assignment.shift_id,
                  targetShiftId,
                  token,
                ));
              }}>Créer une version modifiée</button>
            </div>
          )}

          {selected.tool_calls.length > 0 && (
            <div className="journal-panel">
              <h3>Journal de l'agent</h3>
              <p className="eyebrow">
                Session {selected.agent_session_id} · Requête {selected.agent_request_id}
              </p>
              <ol>
                {selected.tool_calls.map((call, index) => (
                  <li key={`${call.tool}-${call.timestamp}-${index}`}>
                    <strong>{call.tool}</strong> — {call.status}
                    <small> ({new Date(call.timestamp).toLocaleTimeString()})</small>
                  </li>
                ))}
              </ol>
            </div>
          )}

          <div className="publish-panel">
            <h3>Approbation et publication</h3>
            {selected.status === "draft" && (
              <button disabled={busy} type="button" onClick={() => void handlePublish()}>
                Publier V{selected.revision}
              </button>
            )}
            {selected.status === "published" && (
              <>
                <p className="notice">Version publiée{selected.approved_at ? ` le ${new Date(selected.approved_at).toLocaleString()}` : ""}.</p>
                <button disabled={busy} type="button" onClick={() => void handleDispatch()}>
                  Envoyer les notifications
                </button>
              </>
            )}
            {selected.status === "superseded" && <p className="notice">Version remplacée par une publication plus récente.</p>}
            {outbox.length > 0 && (
              <ul className="outbox-list">
                {outbox.map((item) => (
                  <li key={item.id}>
                    <strong>{item.channel}</strong> → {item.recipient} — {item.status}
                    {item.attempt_count > 0 && <small> ({item.attempt_count} tentative{item.attempt_count > 1 ? "s" : ""})</small>}
                    {item.last_error && <small className="error"> {item.last_error}</small>}
                  </li>
                ))}
              </ul>
            )}
          </div>

          {diff && (
            <div className="diff-panel">
              <h3>Diff avec la version précédente</h3>
              {diff.added.map((item) => <p className="diff-added" key={`add-${item}`}>+ {item}</p>)}
              {diff.removed.map((item) => <p className="diff-removed" key={`remove-${item}`}>− {item}</p>)}
              {!diff.added.length && !diff.removed.length && <p>Aucune affectation modifiée.</p>}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
