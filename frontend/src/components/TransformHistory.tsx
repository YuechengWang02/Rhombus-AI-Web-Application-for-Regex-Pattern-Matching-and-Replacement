import type { Transformation } from "../api/types";

interface Props {
  items: Transformation[];
  latestUndoableId: string | null;
  onUndo: (id: string) => void;
  busy?: boolean;
}

function describeColumns(columns: string[]): string {
  if (columns.length === 0) return "all text columns";
  if (columns.length <= 3) return columns.join(", ");
  return `${columns.length} columns`;
}

function describe(t: Transformation): string {
  const where = describeColumns(t.columns);
  if (t.kind === "regex") {
    return `Replace /${t.regex_pattern}/ → "${t.replacement}" in ${where}`;
  }
  if (t.kind === "dates") return `Standardize dates in ${where}`;
  if (t.kind === "phones") return `Normalize phone numbers in ${where}`;
  return `${t.kind} on ${where}`;
}

/** History list; only the most recent active transform can be undone. */
export function TransformHistory({
  items,
  latestUndoableId,
  onUndo,
  busy = false,
}: Props) {
  if (items.length === 0) return null;
  return (
    <div className="card">
      <span className="label">History</span>
      <ul className="history">
        {items.map((t) => (
          <li key={t.id} className={t.is_undone ? "history__undone" : ""}>
            <span>
              {describe(t)} · {t.match_count} change
              {t.match_count === 1 ? "" : "s"}
              {t.is_undone && " (undone)"}
            </span>
            {!t.is_undone && t.id === latestUndoableId && (
              <button type="button" disabled={busy} onClick={() => onUndo(t.id)}>
                Undo
              </button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
