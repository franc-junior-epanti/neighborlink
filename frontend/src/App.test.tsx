import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { App } from "./App";

describe("App", () => {
  it("shows the NeighborLink promise", () => {
    render(<App />);
    expect(screen.getByRole("heading")).toHaveTextContent(
      "Coordinate people. Strengthen communities.",
    );
  });
});
