const http = require("http");

const targetPort = Number(process.env.RSDW_UI_PORT || 4317);
const listenPort = Number(process.env.RSDW_SHARE_PORT || 4418);
const listenHost = "0.0.0.0";

const server = http.createServer((req, res) => {
  const headers = { ...req.headers };
  headers.host = `127.0.0.1:${targetPort}`;
  headers["x-forwarded-for"] = req.socket.remoteAddress || "";
  headers["x-forwarded-host"] = req.headers.host || "";
  headers["x-forwarded-proto"] = "http";

  const proxy = http.request({
    hostname: "127.0.0.1",
    port: targetPort,
    path: req.url,
    method: req.method,
    headers,
  }, (upstream) => {
    res.writeHead(upstream.statusCode || 502, upstream.headers);
    upstream.pipe(res);
  });

  proxy.on("error", (error) => {
    if (!res.headersSent) res.writeHead(502, { "content-type": "application/json" });
    res.end(JSON.stringify({ ok: false, error: "RSDW sharing proxy unavailable", detail: error.message }));
  });

  req.pipe(proxy);
});

server.listen(listenPort, listenHost, () => {
  process.stdout.write(`RSDW share proxy listening on ${listenHost}:${listenPort} -> 127.0.0.1:${targetPort}\n`);
});

const shutdown = () => server.close(() => process.exit(0));
process.on("SIGTERM", shutdown);
process.on("SIGINT", shutdown);
