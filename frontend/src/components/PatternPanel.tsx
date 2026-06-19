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

interface Props {
  textColumns: string[];
  column: string;
  onColumnChange: (column: string) => void;
  generated: GenerateRegexResponse | null;
  busy: BusyAction;
  onGenerate: (description: string) => void;
  onPreview: (body: ReplacementBody) => void;
  onApply: (body: ReplacementBody) => void;
  onCreative: (kind: "dates" | "phones", mode: "preview" | "apply", description: string) => void;
}

/**
 * Controls for describing a pattern, generating a regex, and previewing/applying
 * a replacement — plus shortcuts for the two creative transforms.
 */
export function PatternPanel({
  textColumns,
  column,
  onColumnChange,
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
  const [replacement, setReplacement] = useState("");

  // Seed the editable regex fields whenever a new pattern is generated.
  useEffect(() => {
    if (generated) {
      setRegex(generated.regex);
      setFlags(generated.flags);
    }
  }, [generated]);

  const anyBusy = busy !== null;
  const hasColumn = column !== "";
  const replaceBody: ReplacementBody = {
    column,
    regex,
    flags,
    replacement,
    description,
  };

  return (
    <div className="card panel">
      <label className="field">
        <span className="label">Column</span>
        <select
          value={column}
          onChange={(e) => onColumnChange(e.target.value)}
          disabled={textColumns.length === 0}
        >
          <option value="">Select a text column…</option>
          {textColumns.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
      </label>

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
          disabled={anyBusy || !hasColumn || !regex}
          onClick={() => onPreview(replaceBody)}
        >
          {busy === "preview" ? "Previewing…" : "Preview"}
        </button>
        <button
          type="button"
          className="primary"
          disabled={anyBusy || !hasColumn || !regex}
          onClick={() => onApply(replaceBody)}
        >
          {busy === "apply" ? "Applying…" : "Apply replacement"}
        </button>
      </div>

      <fieldset className="creative">
        <legend>Creative transforms (LLM-powered)</legend>
        <p className="muted">
          Operate on the selected column using a natural-language hint (optional).
        </p>
        <div className="row">
          <button
            type="button"
            disabled={anyBusy || !hasColumn}
            onClick={() => onCreative("dates", "apply", description)}
          >
            {busy === "dates" ? "Working…" : "Standardize dates"}
          </button>
          <button
            type="button"
            disabled={anyBusy || !hasColumn}
            onClick={() => onCreative("phones", "apply", description)}
          >
            {busy === "phones" ? "Working…" : "Normalize phones"}
          </button>
        </div>
      </fieldset>
    </div>
  );
}
