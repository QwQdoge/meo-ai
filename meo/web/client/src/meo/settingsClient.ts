export async function settingsRequest<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(`/api/meo${path}`, {
    ...init,
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  const value = await response.json().catch(() => ({}));
  if (!response.ok) {
    const code = value && typeof value === "object" &&
      "error" in value && value.error && typeof value.error === "object" &&
      "code" in value.error && typeof value.error.code === "string"
      ? value.error.code : "";
    // Only stable, user-safe capability errors are shown. Do not relay raw
    // vendor diagnostics, stack traces or network failure payloads.
    const safeCode = /^(?:mcp_[a-z_]+|catalog_[a-z_]+|invalid_(?:skill_source|skill_content|catalog_search|catalog_cursor))$/.test(code);
    throw new Error(safeCode ? code :
      response.status === 409 ? "conflict" :
        response.status === 404 || response.status === 501 ? "unavailable" : "failed");
  }
  return value as T;
}
