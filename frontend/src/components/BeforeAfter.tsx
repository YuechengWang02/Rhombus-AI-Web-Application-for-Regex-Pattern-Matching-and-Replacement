import type { DiffRow } from "../api/types";

interface Props {
  diffs: DiffRow[];
  totalChanged: number;
}

/** Focused before/after view of cells a replacement/transform would change. */
export function BeforeAfter({ diffs, totalChanged }: Props) {
  if (totalChanged === 0) {
    return <p className="muted">No cells would change with this pattern.</p>;
  }
  return (
    <div className="card">
      <p className="muted">
        {totalChanged} cell{totalChanged === 1 ? "" : "s"} would change
        {diffs.length < totalChanged && ` (showing first ${diffs.length})`}.
      </p>
      <table className="diff">
        <thead>
          <tr>
            <th>Row</th>
            <th>Before</th>
            <th>After</th>
          </tr>
        </thead>
        <tbody>
          {diffs.map((d) => (
            <tr key={d.row}>
              <td>{d.row + 1}</td>
              <td className="diff__before">{d.before ?? ""}</td>
              <td className="diff__after">{d.after ?? ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
