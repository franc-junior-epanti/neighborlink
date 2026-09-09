import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

vi.mock("./auth/AuthContext", () => ({
  useAuth: () => ({
    ready: true,
    authenticated: true,
    username: "tester@example.test",
    getAccessToken: async () => "test-token",
    signOut: async () => undefined,
  }),
}));

describe("App", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          user_id: "user-id",
          display_name: "Tester",
          email: "tester@example.test",
          organizations: [],
        }),
      }),
    );
  });

  it("shows the NeighborLink promise", async () => {
    render(<App />);
    expect(screen.getByRole("heading")).toHaveTextContent(
      "Coordinate people. Strengthen communities.",
    );
  });
});
