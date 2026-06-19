import { describe, it, expect, vi, afterEach } from "vitest";
import { api, ApiRequestError } from "./client";

function mockFetchOnce(resp: Partial<Response> & { json: () => Promise<unknown> }) {
  globalThis.fetch = vi.fn().mockResolvedValue(resp as Response);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("api client", () => {
  it("parses JSON on success", async () => {
    mockFetchOnce({
      ok: true,
      json: async () => ({
        rows: [],
        page: 1,
        size: 50,
        total_rows: 0,
        total_pages: 0,
      }),
    });
    const res = await api.rows("abc", 1, 50);
    expect(res.total_rows).toBe(0);
  });

  it("throws ApiRequestError carrying status, code, and detail", async () => {
    mockFetchOnce({
      ok: false,
      status: 422,
      json: async () => ({ error: "unprocessable", detail: "bad regex" }),
    });
    await expect(
      api.previewReplace("abc", { column: "c", regex: "(", replacement: "" }),
    ).rejects.toMatchObject({
      status: 422,
      code: "unprocessable",
      message: "bad regex",
    });
  });

  it("flattens DRF field errors into a message", async () => {
    mockFetchOnce({
      ok: false,
      status: 400,
      json: async () => ({ error: "validation_error", detail: { column: ["required"] } }),
    });
    await expect(api.rows("a", 1, 50)).rejects.toMatchObject({
      message: "column: required",
    });
  });

  it("wraps network failures as a network error", async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error("offline"));
    await expect(api.rows("a", 1, 50)).rejects.toBeInstanceOf(ApiRequestError);
    await expect(api.rows("a", 1, 50)).rejects.toMatchObject({
      code: "network_error",
    });
  });
});
