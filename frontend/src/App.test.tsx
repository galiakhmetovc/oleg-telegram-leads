import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import { App } from "./App";

test("renders the v2 workspace shell", () => {
  render(<App />);

  expect(screen.getByRole("heading", { name: "PUR Leads v2" })).toBeInTheDocument();
  expect(screen.getByText("PostgreSQL")).toBeInTheDocument();
  expect(screen.getByText("FastAPI")).toBeInTheDocument();
  expect(screen.getByText("React")).toBeInTheDocument();
});
