import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FileUpload } from "./FileUpload";

function fileInput(): HTMLInputElement {
  return document.querySelector('input[type="file"]') as HTMLInputElement;
}

describe("FileUpload", () => {
  it("rejects an unsupported file type and shows an error", async () => {
    const onUpload = vi.fn();
    render(<FileUpload onUpload={onUpload} />);
    const bad = new File(["x"], "notes.txt", { type: "text/plain" });
    // applyAccept:false so the browser's accept filter doesn't pre-empt our
    // own validation logic (which is what we're testing here).
    await userEvent.upload(fileInput(), bad, { applyAccept: false });

    expect(onUpload).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent(/unsupported file type/i);
  });

  it("accepts a CSV file and calls onUpload", async () => {
    const onUpload = vi.fn();
    render(<FileUpload onUpload={onUpload} />);
    const good = new File(["a,b\n1,2"], "data.csv", { type: "text/csv" });
    await userEvent.upload(fileInput(), good);

    expect(onUpload).toHaveBeenCalledTimes(1);
    expect(onUpload.mock.calls[0][0].name).toBe("data.csv");
  });
});
