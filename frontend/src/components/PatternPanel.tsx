import { useEffect, useState } from "react";
import type { GenerateRegexResponse } from "../api/types";
import type { ReplacementBody } from "../api/client";

export type BusyAction =
  | "generate"
  | "preview"
  | "apply"
  | "dates"
  | "phones"
  | null;

export interface Scope {
  applyToAll: boolean;
  selectedColumns: string[];
}

interface Props {
  textColumns: string[];
  scope: Scope;
  onScopeChange: (scope: Scope) => void;
  generated: GenerateRegexResponse | null;
  busy: BusyAction;
  onGenerate: (description: string) => void;
  onPreview: (body: ReplacementBody) => void;
  onApply: (body: ReplacementBody) => void;
  onCreative: (kind: "dates" | "phones", mode: "preview" | "apply", description: string) => void;
}

/**
 * Controls for choosing which text columns to target, describing a pattern,
 * generating a regex, and previewing/applying a replacement — plus the two
 * creative transforms. The replacement applies to every selected column at once
 * (default: all text columns).
 */
export function PatternPanel({
  textColumns,
  scope,
  onScopeChange,
  generated,
  busy,
  onGenerate,
  onPreview,
  onApply,
  onCreative,
}: Props) {
  const [description, setDescription] = useState("");
  const [regex, setRegex] = useState("");
  const [flags, setFlags] = useState("");
  // Default matches the assignment's example ("…replace them with 'REDACTED'").
  const [replacement, setReplacement] = useState("REDACTED");

  // Seed the editable regex fields whenever a new pattern is generated.
  useEffect(() => {
    if (generated) {
      setRegex(generated.regex);
      setFlags(generated.flags);
    }
  }, [generated]);

  const anyBusy = busy !== null;
  const hasScope = scope.applyToAll || scope.selectedColumns.length > 0;
  // Date/phone transforms rewrite whole cells, so they must target specific
  // columns — never "all text columns" (that would mangle unrelated columns).
  const creativeReady = !scope.applyToAll && scope.selectedColumns.length > 0;
  // Columns are injected by App from the shared scope — body carries the rest.
  const replaceBody: ReplacementBody = { regex, flags, replacement, description };

  const toggleColumn = (col: string) => {
    const selected = scope.selectedColumns.includes(col)
      ? scope.selectedColumns.filter((c) => c !== col)
      : [...scope.selectedColumns, col];
    onScopeChange({ applyToAll: false, selectedColumns: selected });
  };

  return (
    <div className="card panel">
      <div className="field">
        <span className="label">Apply to</span>
        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={scope.applyToAll}
            disabled={textColumns.length === 0}
            onChange={(e) =>
              onScopeChange({ applyToAll: e.target.checked, selectedColumns: [] })
            }
          />
          All text columns ({textColumns.length})
        </label>
        {!scope.applyToAll && (
          <div className="column-picker">
            {textColumns.map((c) => (
              <label key={c} className="checkbox-row">
                <input
                  type="checkbox"
                  checked={scope.selectedColumns.includes(c)}
                  onChange={() => toggleColumn(c)}
                />
                {c}
              </label>
            ))}
          </div>
        )}
      </div>

      <label className="field">
        <span className="label">Describe the pattern</span>
        <textarea
          value={description}
          placeholder='e.g. "find email addresses"'
          onChange={(e) => setDescription(e.target.value)}
          rows={2}
        />
      </label>

      <button
        type="button"
        disabled={anyBusy || !description.trim()}
        onClick={() => onGenerate(description)}
      >
        {busy === "generate" ? "Generating…" : "Generate regex"}
      </button>

      <label className="field">
        <span className="label">Regex pattern</span>
        <input
          value={regex}
          onChange={(e) => setRegex(e.target.value)}
          placeholder="Generated pattern appears here (editable)"
          spellCheck={false}
        />
      </label>

      <div className="row">
        <label className="field field--narrow">
          <span className="label">Flags</span>
          <input
            value={flags}
            onChange={(e) => setFlags(e.target.value)}
            placeholder="imsx"
            spellCheck={false}
          />
        </label>
        <label className="field">
          <span className="label">Replacement value</span>
          <input
            value={replacement}
            onChange={(e) => setReplacement(e.target.value)}
            placeholder="e.g. REDACTED"
          />
        </label>
      </div>

      <div className="row">
        <button
          type="button"
          disabled={anyBusy || !hasScope || !regex}
          onClick={() => onPreview(replaceBody)}
        >
          {busy === "preview" ? "Previewing…" : "Preview"}
        </button>
        <button
          type="button"
          className="primary"
          disabled={anyBusy || !hasScope || !regex}
          onClick={() => onApply(replaceBody)}
        >
          {busy === "apply" ? "Applying…" : "Apply replacement"}
        </button>
      </div>

      <fieldset className="creative">
        <legend>Creative transforms (LLM-powered)</legend>
        <p className="muted">
          {creativeReady
            ? `Reformats values in: ${scope.selectedColumns.join(", ")}.`
            : "Uncheck “All text columns” and pick the specific date/phone column(s) first — these rewrite whole cells, so they must be targeted."}
        </p>
        <div className="row">
          <button
            type="button"
            disabled={anyBusy || !creativeReady}
            onClick={() => onCreative("dates", "apply", description)}
          >
            {busy === "dates" ? "Working…" : "Standardize dates"}
          </button>
          <button
            type="button"
            disabled={anyBusy || !creativeReady}
            onClick={() => onCreative("phones", "apply", description)}
          >
            {busy === "phones" ? "Working…" : "Normalize phones"}
          </button>
        </div>
      </fieldset>
    </div>
  );
}
