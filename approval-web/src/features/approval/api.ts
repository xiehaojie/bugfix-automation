export async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { cache: "no-store", ...init });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data.ok === false) {
    const method = init?.method ?? "GET";
    const detail = data.error ? `：${data.error}` : "";
    throw new Error(`${method} ${url} 失败 (${response.status})${detail}`);
  }
  return data as T;
}
