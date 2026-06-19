// Typed fetch wrapper around the backend API.
//
// All errors are normalized to `ApiRequestError` so the UI can render a single
// message regardless of where the failure happened (network vs HTTP vs parse).

import type {
  ApplyResponse,
  CreativeApplyResponse,
  CreativePreviewResponse,
  GenerateRegexResponse,
  PreviewResponse,
  RowsPage,
  Transformation,
  UploadResponse,
} from "./types";

// Normalize the API base URL. Render injects the backend hostname without a
// scheme, so default to https:// when one isn't provided.
function normalizeBaseUrl(raw: string | undefined): string {
  const value = (raw ?? "http://localhost:8000").trim().replace(/\/$/, "");
  return /^https?:\/\//i.test(value) ? value : `https://${value}`;
}

const BASE_URL = normalizeBaseUrl(import.meta.env.VITE_API_BASE_URL);

export class ApiRequestError extends Error {
  status: number;
  code: string;
  constructor(message: string, status: number, code: string) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
    this.code = code;
  }
}

function detailToMessage(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object") {
    // DRF field errors -> "field: message".
    const parts = Object.entries(detail).map(
      ([k, v]) => `${k}: ${Array.isArray(v) ? v.join(", ") : String(v)}`,
    );
    if (parts.length) return parts.join("; ");
  }
  return "Request failed.";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, init);
  } catch (err) {
    throw new ApiRequestError(
      "Could not reach the server. Is the backend running?",
      0,
      "network_error",
    );
  }

  if (!response.ok) {
    let code = "request_error";
    let message = `Request failed (${response.status}).`;
    try {
      const body = await response.json();
      code = body.error ?? code;
      message = detailToMessage(body.detail ?? body);
    } catch {
      /* non-JSON error body; keep defaults */
    }
    throw new ApiRequestError(message, response.status, code);
  }

  return (await response.json()) as T;
}

function postJSON<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export interface ReplacementBody {
  // Omit (or pass an empty list) to target all text columns.
  columns?: string[];
  regex: string;
  flags?: string;
  replacement: string;
  description?: string;
}

export interface CreativeBody {
  // Omit (or pass an empty list) to target all text columns.
  columns?: string[];
  description?: string;
  params?: Record<string, unknown>;
}

export const api = {
  async upload(file: File): Promise<UploadResponse> {
    const form = new FormData();
    form.append("file", file);
    return request<UploadResponse>("/api/uploads/", {
      method: "POST",
      body: form,
    });
  },

  rows(datasetId: string, page: number, size: number): Promise<RowsPage> {
    return request<RowsPage>(
      `/api/uploads/${datasetId}/rows/?page=${page}&size=${size}`,
    );
  },

  generateRegex(body: {
    description: string;
    dataset_id?: string;
    columns?: string[];
  }): Promise<GenerateRegexResponse> {
    return postJSON<GenerateRegexResponse>("/api/regex/generate/", body);
  },

  previewReplace(
    datasetId: string,
    body: ReplacementBody,
  ): Promise<PreviewResponse> {
    return postJSON<PreviewResponse>(`/api/uploads/${datasetId}/preview/`, body);
  },

  applyReplace(
    datasetId: string,
    body: ReplacementBody,
  ): Promise<ApplyResponse> {
    return postJSON<ApplyResponse>(`/api/uploads/${datasetId}/apply/`, body);
  },

  previewCreative(
    datasetId: string,
    kind: string,
    body: CreativeBody,
  ): Promise<CreativePreviewResponse> {
    return postJSON<CreativePreviewResponse>(
      `/api/uploads/${datasetId}/transform/${kind}/preview/`,
      body,
    );
  },

  applyCreative(
    datasetId: string,
    kind: string,
    body: CreativeBody,
  ): Promise<CreativeApplyResponse> {
    return postJSON<CreativeApplyResponse>(
      `/api/uploads/${datasetId}/transform/${kind}/apply/`,
      body,
    );
  },

  transformations(datasetId: string): Promise<Transformation[]> {
    return request<Transformation[]>(
      `/api/uploads/${datasetId}/transforms/`,
    );
  },

  undo(datasetId: string, transformId: string): Promise<RowsPage> {
    return postJSON<RowsPage>(
      `/api/uploads/${datasetId}/transforms/${transformId}/undo/`,
      {},
    );
  },

  downloadUrl(datasetId: string, format: "csv" | "xlsx"): string {
    return `${BASE_URL}/api/uploads/${datasetId}/download/?format=${format}`;
  },
};
