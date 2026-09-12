import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ScheduleBoard } from "./ScheduleBoard";
import * as schedules from "./api/schedules";

vi.mock("./api/schedules");

const firstVersion = {
  id: "version-1",
  operation_id: "operation-1",
  revision: 1,
  status: "draft",
  origin: "agent",
  total_score: 82,
  created_at: "2026-09-11T12:00:00Z",
  score_details: { coverage: 82 },
  conflicts: [],
  explanations: ["Toutes les compétences requises sont couvertes."],
  assignments: [{
    id: "assignment-1",
    volunteer_id: "volunteer-1",
    volunteer_name: "Amina",
    shift_id: "shift-1",
    shift_name: "Accueil",
    starts_at: "2026-09-12T08:00:00Z",
    ends_at: "2026-09-12T10:00:00Z",
    response_status: "proposed",
    reason_codes: ["skill_match"],
    distance_km: 2,
  }],
  shifts: [{
    id: "shift-1",
    name: "Accueil",
    role_name: "Accueil",
    starts_at: "2026-09-12T08:00:00Z",
    ends_at: "2026-09-12T10:00:00Z",
    capacity: 2,
  }],
  agent_session_id: "operation-1",
  agent_request_id: "request-1",
  tool_calls: [
    { tool: "optimize_schedule", status: "completed", timestamp: "2026-09-11T12:00:01Z" },
    { tool: "validate_plan", status: "completed", timestamp: "2026-09-11T12:00:02Z" },
    { tool: "explain_plan", status: "completed", timestamp: "2026-09-11T12:00:03Z" },
  ],
  approved_at: null,
};

describe("ScheduleBoard", () => {
  beforeEach(() => {
    vi.mocked(schedules.fetchOperations).mockResolvedValue([{
      id: "operation-1",
      name: "Journée Douala",
      event_date: "2026-09-12",
      location_name: "Douala",
      status: "draft",
    }]);
    vi.mocked(schedules.fetchVersions).mockResolvedValue([firstVersion]);
    vi.mocked(schedules.fetchVersion).mockResolvedValue(firstVersion);
    vi.mocked(schedules.fetchDiff).mockResolvedValue({
      base_version_id: null,
      target_version_id: "version-1",
      added: [],
      removed: [],
    });
    vi.mocked(schedules.generateVersion).mockResolvedValue({
      ...firstVersion,
      id: "version-2",
      revision: 2,
    });
  });

  it("affiche une version et demande un nouveau brouillon à l’agent", async () => {
    render(
      <ScheduleBoard
        organizationId="organization-1"
        getAccessToken={async () => "token"}
      />,
    );

    expect(await screen.findByText("Amina")).toBeInTheDocument();
    expect(screen.getByText("82")).toBeInTheDocument();
    expect(screen.getByText("Journal de l'agent")).toBeInTheDocument();
    expect(screen.getByText(/request-1/)).toBeInTheDocument();
    expect(screen.getAllByText(/optimize_schedule/).length).toBeGreaterThan(0);
    fireEvent.change(screen.getByPlaceholderText("Ex. privilégie les bénévoles proches"), {
      target: { value: "Privilégie les bénévoles disponibles" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Générer un nouveau brouillon" }));

    await waitFor(() => expect(schedules.generateVersion).toHaveBeenCalledWith(
      "operation-1",
      "Privilégie les bénévoles disponibles",
      "token",
    ));
  });

  it("publie une version brouillon puis affiche l’outbox après envoi", async () => {
    const published = {
      ...firstVersion,
      status: "published",
      approved_at: "2026-09-12T09:00:00Z",
    };
    const outboxItem = {
      id: "outbox-1",
      assignment_id: "assignment-1",
      channel: "email",
      recipient: "amina@example.dev",
      mode: "simulated",
      status: "pending",
      attempt_count: 0,
      last_error: null,
    };
    vi.mocked(schedules.publishVersion).mockResolvedValue({
      schedule_version_id: "version-1",
      status: "published",
      approved_at: "2026-09-12T09:00:00Z",
      notifications: [outboxItem],
    });
    vi.mocked(schedules.fetchVersion).mockResolvedValueOnce(firstVersion).mockResolvedValue(published);
    vi.mocked(schedules.fetchOutboxStatus).mockResolvedValue([outboxItem]);
    vi.mocked(schedules.dispatchNotifications).mockResolvedValue({
      notifications: [{ ...outboxItem, status: "simulated", attempt_count: 1 }],
    });

    render(
      <ScheduleBoard
        organizationId="organization-1"
        getAccessToken={async () => "token"}
      />,
    );

    fireEvent.click(await screen.findByRole("button", { name: "Publier V1" }));

    await waitFor(() => expect(schedules.publishVersion).toHaveBeenCalledWith("version-1", 1, "token"));
    expect(await screen.findByText(/amina@example.dev/)).toBeInTheDocument();

    fireEvent.click(await screen.findByRole("button", { name: "Envoyer les notifications" }));
    await waitFor(() => expect(schedules.dispatchNotifications).toHaveBeenCalledWith("version-1", "token"));
    expect(await screen.findByText(/simulated/)).toBeInTheDocument();
  });
});
