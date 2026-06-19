import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// Mock the API client module so the whole App flow runs without a backend.
vi.mock("./api/client", () => {
  class ApiRequestError extends Error {
    status = 0;
    code = "";
  }
  return {
    ApiRequestError,
    api: {
      upload: vi.fn(),
      rows: vi.fn(),
      generateRegex: vi.fn(),
      previewReplace: vi.fn(),
      applyReplace: vi.fn(),
      previewCreative: vi.fn(),
      applyCreative: vi.fn(),
      transformations: vi.fn(),
      undo: vi.fn(),
      downloadUrl: () => "http://localhost:8000/download",
    },
  };
});

import App from "./App";
import { api } from "./api/client";

const dataset = {
  id: "d1",
  original_filename: "people.csv",
  file_type: "csv" as const,
  row_count: 2,
  columns: [
    { name: "Name", dtype: "object", is_text: true },
    { name: "Email", dtype: "object", is_text: true },
  ],
  text_columns: ["Name", "Email"],
  created_at: "",
  expires_at: "",
};

const uploadResponse = {
  dataset,
  rows: [
    { Name: "John Doe", Email: "john@example.com" },
    { Name: "Jane Smith", Email: "jane@example.com" },
  ],
  page: 1,
  size: 50,
  total_rows: 2,
  total_pages: 1,
};

beforeEach(() => {
  vi.clearAllMocks();
});

function uploadFile() {
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  const file = new File(["x"], "people.csv", { type: "text/csv" });
  return userEvent.upload(input, file);
}

describe("App workflow", () => {
  it("uploads a file and renders the data grid", async () => {
    (api.upload as ReturnType<typeof vi.fn>).mockResolvedValue(uploadResponse);
    render(<App />);
    await uploadFile();

    expect(await screen.findByText("john@example.com")).toBeInTheDocument();
    expect(screen.getByText(/Loaded 2 rows/)).toBeInTheDocument();
  });

  it("applies a regex replacement and records history", async () => {
    (api.upload as ReturnType<typeof vi.fn>).mockResolvedValue(uploadResponse);
    (api.applyReplace as ReturnType<typeof vi.fn>).mockResolvedValue({
      transformation: {
        id: "t1",
        kind: "regex",
        columns: ["Email"],
        nl_description: "",
        regex_pattern: ".+@.+",
        flags: "",
        replacement: "REDACTED",
        params: {},
        match_count: 2,
        is_undone: false,
        created_at: "",
      },
      match_count: 2,
      changed_count: 2,
      rows: [
        { Name: "John Doe", Email: "REDACTED" },
        { Name: "Jane Smith", Email: "REDACTED" },
      ],
      page: 1,
      size: 50,
      total_rows: 2,
      total_pages: 1,
    });
    (api.transformations as ReturnType<typeof vi.fn>).mockResolvedValue([
      {
        id: "t1",
        kind: "regex",
        columns: ["Email"],
        nl_description: "",
        regex_pattern: ".+@.+",
        flags: "",
        replacement: "REDACTED",
        params: {},
        match_count: 2,
        is_undone: false,
        created_at: "",
      },
    ]);

    render(<App />);
    await uploadFile();
    await screen.findByText("john@example.com");

    // Default scope is "all text columns"; just enter a regex. The replacement
    // field already defaults to "REDACTED", so clear before retyping.
    await userEvent.type(screen.getByLabelText("Regex pattern"), ".+@.+");
    const replacementInput = screen.getByLabelText("Replacement value");
    await userEvent.clear(replacementInput);
    await userEvent.type(replacementInput, "REDACTED");
    await userEvent.click(screen.getByRole("button", { name: "Apply replacement" }));

    // Grid now shows redacted values and history lists the transformation.
    const cells = await screen.findAllByText("REDACTED");
    expect(cells.length).toBeGreaterThanOrEqual(2);
    // Apply-to-all sends no explicit columns (undefined = all text columns).
    expect(api.applyReplace).toHaveBeenCalledWith(
      "d1",
      expect.objectContaining({ columns: undefined, replacement: "REDACTED" }),
    );
    expect(screen.getByText(/Replace .* in Email/)).toBeInTheDocument();
  });

  it("surfaces API errors as an alert", async () => {
    const { ApiRequestError } = await import("./api/client");
    (api.upload as ReturnType<typeof vi.fn>).mockRejectedValue(
      new ApiRequestError("File too large.", 400, "validation_error"),
    );
    render(<App />);
    await uploadFile();
    expect(await screen.findByRole("alert")).toHaveTextContent("File too large.");
  });
});
