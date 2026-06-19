// Shared API types mirroring the Django/DRF backend responses.

export interface ColumnMeta {
  name: string;
  dtype: string;
  is_text: boolean;
}

export interface Dataset {
  id: string;
  original_filename: string;
  file_type: "csv" | "xlsx";
  row_count: number;
  columns: ColumnMeta[];
  text_columns: string[];
  created_at: string;
  expires_at: string;
}

export type Row = Record<string, unknown>;

export interface RowsPage {
  rows: Row[];
  page: number;
  size: number;
  total_rows: number;
  total_pages: number;
}

export interface UploadResponse extends RowsPage {
  dataset: Dataset;
}

export interface GenerateRegexResponse {
  regex: string;
  flags: string;
  explanation: string;
  confidence: number;
  sample_matches: string[];
}

export interface DiffRow {
  row: number;
  before: string | null;
  after: string | null;
}

export interface PreviewResponse {
  column: string;
  match_count: number;
  changed_count: number;
  diffs: DiffRow[];
  page: number;
  size: number;
  total_changed: number;
}

export type TransformKind = "regex" | "dates" | "phones";

export interface Transformation {
  id: string;
  kind: TransformKind;
  column: string;
  nl_description: string;
  regex_pattern: string;
  flags: string;
  replacement: string;
  params: Record<string, unknown>;
  match_count: number;
  is_undone: boolean;
  created_at: string;
}

export interface ApplyResponse extends RowsPage {
  transformation: Transformation;
  match_count: number;
  changed_count: number;
}

export interface CreativePreviewResponse {
  kind: TransformKind;
  column: string;
  spec: Record<string, unknown>;
  info: Record<string, unknown>;
  changed_count: number;
  diffs: DiffRow[];
  page: number;
  size: number;
  total_changed: number;
}

export interface CreativeApplyResponse extends RowsPage {
  transformation: Transformation;
  info: Record<string, unknown>;
  changed_count: number;
}

export interface ApiError {
  error: string;
  detail: unknown;
}
