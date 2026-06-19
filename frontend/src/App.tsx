import { useCallback, useMemo, useState } from "react";
import { api, ApiRequestError, type ReplacementBody } from "./api/client";
import type {
  Dataset,
  GenerateRegexResponse,
  PreviewResponse,
  RowsPage,
  Transformation,
} from "./api/types";
import { FileUpload } from "./components/FileUpload";
import { DataGrid } from "./components/DataGrid";
import { PatternPanel, type BusyAction } from "./components/PatternPanel";
import { RegexPreview } from "./components/RegexPreview";
import { BeforeAfter } from "./components/BeforeAfter";
import { TransformHistory } from "./components/TransformHistory";

const PAGE_SIZE = 50;

type Busy = BusyAction | "upload" | "undo";

export default function App() {
  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [page, setPage] = useState<RowsPage | null>(null);
  const [column, setColumn] = useState("");
  const [generated, setGenerated] = useState<GenerateRegexResponse | null>(null);
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [history, setHistory] = useState<Transformation[]>([]);
  const [busy, setBusy] = useState<Busy>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const latestUndoableId = useMemo(() => {
    const active = history.filter((t) => !t.is_undone);
    return active.length ? active[active.length - 1].id : null;
  }, [history]);

  /** Run an async action with shared busy/error handling. */
  const run = useCallback(
    async (action: Busy, fn: () => Promise<void>) => {
      setBusy(action);
      setError(null);
      try {
        await fn();
      } catch (err) {
        const message =
          err instanceof ApiRequestError ? err.message : "Something went wrong.";
        setError(message);
      } finally {
        setBusy(null);
      }
    },
    [],
  );

  const refreshHistory = useCallback(async (datasetId: string) => {
    setHistory(await api.transformations(datasetId));
  }, []);

  const handleUpload = (file: File) =>
    run("upload", async () => {
      const res = await api.upload(file);
      setDataset(res.dataset);
      setPage(res);
      setColumn(res.dataset.text_columns[0] ?? "");
      setGenerated(null);
      setPreview(null);
      setHistory([]);
      setNotice(`Loaded ${res.dataset.row_count} rows from ${res.dataset.original_filename}.`);
    });

  const changePage = (next: number) =>
    dataset &&
    run(null, async () => {
      setPage(await api.rows(dataset.id, next, PAGE_SIZE));
    });

  const handleGenerate = (description: string) =>
    dataset &&
    run("generate", async () => {
      setPreview(null);
      setGenerated(
        await api.generateRegex({
          description,
          dataset_id: dataset.id,
          column: column || undefined,
        }),
      );
    });

  const handlePreview = (body: ReplacementBody) =>
    dataset &&
    run("preview", async () => {
      setPreview(await api.previewReplace(dataset.id, body));
    });

  const handleApply = (body: ReplacementBody) =>
    dataset &&
    run("apply", async () => {
      const res = await api.applyReplace(dataset.id, body);
      setPage(res);
      setPreview(null);
      await refreshHistory(dataset.id);
      setNotice(`Applied replacement — ${res.match_count} match(es) updated.`);
    });

  const handleCreative = (
    kind: "dates" | "phones",
    _mode: "preview" | "apply",
    description: string,
  ) =>
    dataset &&
    run(kind, async () => {
      const res = await api.applyCreative(dataset.id, kind, { column, description });
      setPage(res);
      setPreview(null);
      await refreshHistory(dataset.id);
      setNotice(`${kind === "dates" ? "Standardized dates" : "Normalized phones"} — ${res.changed_count} cell(s) changed.`);
    });

  const handleUndo = (id: string) =>
    dataset &&
    run("undo", async () => {
      setPage(await api.undo(dataset.id, id));
      await refreshHistory(dataset.id);
      setNotice("Reverted the last transformation.");
    });

  return (
    <main className="app">
      <header>
        <h1>Regex Pattern Matching &amp; Replacement</h1>
        <p className="muted">
          Upload a CSV/Excel file, describe a pattern in plain English, and apply
          replacements to a text column.
        </p>
      </header>

      <FileUpload onUpload={handleUpload} busy={busy === "upload"} />

      {error && (
        <p role="alert" className="error banner">
          {error}
        </p>
      )}
      {notice && !error && (
        <p role="status" className="notice banner">
          {notice}
        </p>
      )}

      {dataset && page && (
        <section className="workspace">
          <div className="workspace__left">
            <PatternPanel
              textColumns={dataset.text_columns}
              column={column}
              onColumnChange={setColumn}
              generated={generated}
              busy={(busy === "upload" || busy === "undo" ? null : busy) as BusyAction}
              onGenerate={handleGenerate}
              onPreview={handlePreview}
              onApply={handleApply}
              onCreative={handleCreative}
            />
            {generated && <RegexPreview result={generated} />}
            {preview && (
              <BeforeAfter
                diffs={preview.diffs}
                totalChanged={preview.total_changed}
              />
            )}
            <TransformHistory
              items={history}
              latestUndoableId={latestUndoableId}
              onUndo={handleUndo}
              busy={busy === "undo"}
            />
          </div>

          <div className="workspace__right">
            <div className="toolbar">
              <a
                className="button"
                href={api.downloadUrl(dataset.id, "csv")}
                target="_blank"
                rel="noreferrer"
              >
                Download CSV
              </a>
              <a
                className="button"
                href={api.downloadUrl(dataset.id, "xlsx")}
                target="_blank"
                rel="noreferrer"
              >
                Download Excel
              </a>
            </div>
            <DataGrid
              columns={dataset.columns}
              rows={page.rows}
              page={page.page}
              totalPages={page.total_pages}
              totalRows={page.total_rows}
              onPageChange={changePage}
            />
          </div>
        </section>
      )}
    </main>
  );
}
