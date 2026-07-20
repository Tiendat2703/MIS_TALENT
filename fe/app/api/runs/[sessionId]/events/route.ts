const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8080"
).replace(/\/+$/, "");

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ sessionId: string }> },
) {
  const { sessionId } = await params;

  if (!/^\d+$/.test(sessionId)) {
    return new Response("Invalid session id", { status: 400 });
  }

  try {
    const upstream = await fetch(`${API_BASE_URL}/runs/${sessionId}/events`, {
      cache: "no-store",
      headers: {
        Accept: "text/event-stream",
        "Cache-Control": "no-cache",
        "ngrok-skip-browser-warning": "true",
      },
      signal: request.signal,
    });

    if (!upstream.ok || !upstream.body) {
      const detail = await upstream.text();
      return new Response(detail || `Event API returned ${upstream.status}`, {
        status: upstream.status || 502,
      });
    }

    return new Response(upstream.body, {
      status: 200,
      headers: {
        "Content-Type": "text/event-stream; charset=utf-8",
        "Cache-Control": "no-cache, no-transform",
        "X-Accel-Buffering": "no",
      },
    });
  } catch (error) {
    if (request.signal.aborted) {
      return new Response(null, { status: 499 });
    }

    return new Response(
      error instanceof Error ? error.message : "Unable to connect to event API",
      { status: 502 },
    );
  }
}
