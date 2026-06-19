import { useMemo, type ReactNode } from "react";
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from "@tanstack/react-table";
import type { ColumnMeta, Row } from "../api/types";

interface Props {
  columns: ColumnMeta[];
  rows: Row[];
  page: number;
  totalPages: number;
  totalRows: number;
  onPageChange: (page: number) => void;
  // Replacement tokens to bold in the grid (e.g. "REDACTED", "[EMAIL]").
  highlights?: string[];
}

const helper = createColumnHelper<Row>();

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Render a cell, bolding any occurrence of an applied replacement token. */
function renderCell(value: unknown, highlights: string[]): ReactNode {
  if (value === null || value === undefined) return "";
  const text = String(value);
  if (highlights.length === 0) return text;

  const pattern = new RegExp(`(${highlights.map(escapeRegExp).join("|")})`, "g");
  const segments = text.split(pattern);
  return segments.map((seg, i) =>
    highlights.includes(seg) ? (
      <strong key={i} className="redacted">
        {seg}
      </strong>
    ) : (
      seg
    ),
  );
}

/** Paginated read-only table built on TanStack Table. */
export function DataGrid({
  columns,
  rows,
  page,
  totalPages,
  totalRows,
  onPageChange,
  highlights = [],
}: Props) {
  const tableColumns = useMemo(
    () =>
      columns.map((col) =>
        helper.accessor((row) => row[col.name], {
          id: col.name,
          header: () => (
            <span>
              {col.name}
              {col.is_text && <span className="badge" title="Text column">T</span>}
            </span>
          ),
          cell: (info) => renderCell(info.getValue(), highlights),
        }),
      ),
    [columns, highlights],
  );

  const table = useReactTable({
    data: rows,
    columns: tableColumns,
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <div className="grid">
      <div className="grid__scroll">
        <table>
          <thead>
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id}>
                {hg.headers.map((header) => (
                  <th key={header.id}>
                    {flexRender(
                      header.column.columnDef.header,
                      header.getContext(),
                    )}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => (
              <tr key={row.id}>
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id}>
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="grid__pager">
        <button
          type="button"
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
        >
          Previous
        </button>
        <span>
          Page {page} of {totalPages || 1} · {totalRows} rows
        </span>
        <button
          type="button"
          disabled={page >= totalPages}
          onClick={() => onPageChange(page + 1)}
        >
          Next
        </button>
      </div>
    </div>
  );
}
