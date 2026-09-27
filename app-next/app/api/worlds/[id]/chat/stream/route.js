const sup = require("@/lib/supervisor");
const ra = require("@/lib/remoteauth");
export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export async function GET(req, { params }) {
  const denied = ra.guardResponse(req, { worldId: params.id, tab: "chat" });
  if (denied) return denied;
  const worldId = params.id;
  const encoder = new TextEncoder();
  let unsub = null;
  const stream = new ReadableStream({
    start(controller) {
      for (const entry of sup.getChat(worldId).slice(-100)) {
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(entry)}\n\n`));
      }
      unsub = sup.subscribeChat(worldId, (entry) => {
        try { controller.enqueue(encoder.encode(`data: ${JSON.stringify(entry)}\n\n`)); } catch {}
      });
    },
    cancel() { if (unsub) unsub(); },
  });
  return new Response(stream, {
    headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache, no-transform", Connection: "keep-alive" },
  });
}
