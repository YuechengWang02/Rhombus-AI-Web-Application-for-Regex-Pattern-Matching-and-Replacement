import { useId, useRef, useState } from "react";

const ACCEPTED = [".csv", ".xlsx", ".xls"];
const MAX_MB = 25;

function validate(file: File): string | null {
  const lower = file.name.toLowerCase();
  if (!ACCEPTED.some((ext) => lower.endsWith(ext))) {
    return "Unsupported file type. Please choose a .csv, .xlsx, or .xls file.";
  }
  if (file.size > MAX_MB * 1024 * 1024) {
    return `File too large. Maximum size is ${MAX_MB} MB.`;
  }
  return null;
}

interface Props {
  onUpload: (file: File) => void;
  busy?: boolean;
}

/** Drag-and-drop + click file picker with client-side validation. */
export function FileUpload({ onUpload, busy = false }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const inputId = useId();
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function handleFile(file: File | undefined) {
    if (!file) return;
    const problem = validate(file);
    if (problem) {
      setError(problem);
      return;
    }
    setError(null);
    onUpload(file);
  }

  return (
    <div>
      <div
        role="button"
        tabIndex={0}
        aria-label="Upload CSV or Excel file"
        className={`dropzone${dragging ? " dropzone--active" : ""}`}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") inputRef.current?.click();
        }}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          handleFile(e.dataTransfer.files?.[0]);
        }}
      >
        <input
          id={inputId}
          ref={inputRef}
          type="file"
          accept={ACCEPTED.join(",")}
          hidden
          onChange={(e) => handleFile(e.target.files?.[0])}
        />
        <p>{busy ? "Uploading…" : "Drag a CSV/Excel file here, or click to browse"}</p>
        <p className="hint">Accepted: {ACCEPTED.join(", ")} · up to {MAX_MB} MB</p>
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </div>
  );
}
