import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DataGrid } from "./DataGrid";
import type { ColumnMeta } from "../api/types";

const columns: ColumnMeta[] = [
  { name: "ID", dtype: "int64", is_text: false },
  { name: "Email", dtype: "object", is_text: true },
];
const rows = [
  { ID: 1, Email: "john@example.com" },
  { ID: 2, Email: "jane@example.com" },
];

describe("DataGrid", () => {
  it("renders headers and cell values", () => {
    render(
      <DataGrid
        columns={columns}
        rows={rows}
        page={1}
        totalPages={3}
        totalRows={120}
        onPageChange={() => {}}
      />,
    );
    expect(screen.getByText("Email")).toBeInTheDocument();
    expect(screen.getByText("john@example.com")).toBeInTheDocument();
    expect(screen.getByText(/Page 1 of 3/)).toBeInTheDocument();
  });

  it("disables Previous on the first page and pages forward", async () => {
    const onPageChange = vi.fn();
    render(
      <DataGrid
        columns={columns}
        rows={rows}
        page={1}
        totalPages={3}
        totalRows={120}
        onPageChange={onPageChange}
      />,
    );
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(onPageChange).toHaveBeenCalledWith(2);
  });
});
