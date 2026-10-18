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
  if (!response.ok)
    throw new Error(
      response.status === 409
        ? "conflict"
        : response.status === 404 || response.status === 501
          ? "unavailable"
          : "failed",
    );
  return value as T;
}
