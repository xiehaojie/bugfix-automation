const apiUrl = process.env.BUGFIX_API_URL || "http://127.0.0.1:8766";

export async function POST(request: Request) {
  const body = await request.json();
  const resp = await fetch(`${apiUrl}/api/bugs/optimize-prompt`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(120_000),
  });
  const data = await resp.json();
  return Response.json(data, { status: resp.status });
}
