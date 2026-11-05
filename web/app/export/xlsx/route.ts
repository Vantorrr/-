const API_URL = process.env.API_URL || "http://127.0.0.1:8000";

export async function GET(request: Request) {
  const incoming = new URL(request.url);
  const query = new URLSearchParams();
  for (const key of ["status", "source_id", "min_score", "limit"]) {
    const value = incoming.searchParams.get(key);
    if (value) query.set(key, value);
  }
  const response = await fetch(`${API_URL}/api/listings.xlsx?${query.toString()}`, { cache: "no-store" });
  const body = await response.arrayBuffer();
  return new Response(body, {
    status: response.status,
    headers: {
      "content-type":
        response.headers.get("content-type") ||
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      "content-disposition": "attachment; filename=orders.xlsx",
    },
  });
}
