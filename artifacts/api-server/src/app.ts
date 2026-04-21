import http from "http";
import express, { type Express, type Request, type Response } from "express";
import cors from "cors";
import pinoHttp from "pino-http";
import router from "./routes";
import { logger } from "./lib/logger";

const app: Express = express();

app.use(
  pinoHttp({
    logger,
    serializers: {
      req(req) {
        return {
          id: req.id,
          method: req.method,
          url: req.url?.split("?")[0],
        };
      },
      res(res) {
        return {
          statusCode: res.statusCode,
        };
      },
    },
  }),
);
app.use(cors());
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

app.use("/api", router);

// ---------------------------------------------------------------------------
// Proxy all other requests to the Flask webhook dashboard (port 5000)
// express.json() has already consumed the body stream, so we must re-
// serialise req.body when forwarding POST/PUT/PATCH requests.
// ---------------------------------------------------------------------------
app.use((req: Request, res: Response) => {
  // Re-serialise the body that express.json() already parsed.
  const rawBody =
    req.body && Object.keys(req.body).length > 0
      ? Buffer.from(JSON.stringify(req.body), "utf-8")
      : undefined;

  const headers: http.OutgoingHttpHeaders = {
    ...req.headers,
    host: "127.0.0.1:5000",
  };
  if (rawBody) {
    headers["content-type"] = "application/json";
    headers["content-length"] = rawBody.byteLength;
  } else {
    // Avoid sending a stale content-length from the original headers
    delete headers["content-length"];
  }

  const options: http.RequestOptions = {
    hostname: "127.0.0.1",
    port: 5000,
    path: req.url,
    method: req.method,
    headers,
  };

  const proxy = http.request(options, (proxyRes) => {
    res.writeHead(proxyRes.statusCode ?? 502, proxyRes.headers);
    proxyRes.pipe(res, { end: true });
  });

  proxy.on("error", () => {
    if (!res.headersSent) {
      res.status(502).json({ error: "Webhook dashboard is starting up, please retry." });
    }
  });

  if (rawBody) {
    proxy.write(rawBody);
    proxy.end();
  } else {
    req.pipe(proxy, { end: true });
  }
});

export default app;
