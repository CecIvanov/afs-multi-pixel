import { PassThrough } from "node:stream";
import { renderToPipeableStream } from "react-dom/server";
import { ServerRouter, type EntryContext } from "react-router";
import { createReadableStreamFromReadable } from "@react-router/node";
import { isbot } from "isbot";
import { addDocumentResponseHeaders } from "./shopify.server";
import { logError } from "./logger.server";
import { withRequestContext } from "./request-context.server";

export const streamTimeout = 5000;

export default async function handleRequest(
  request: Request,
  responseStatusCode: number,
  responseHeaders: Headers,
  reactRouterContext: EntryContext,
) {
  return withRequestContext(request, undefined, async () => {
    addDocumentResponseHeaders(request, responseHeaders);
    const callbackName = isbot(request.headers.get("user-agent") ?? "") ? "onAllReady" : "onShellReady";

    return new Promise((resolve, reject) => {
      const { pipe, abort } = renderToPipeableStream(
        <ServerRouter context={reactRouterContext} url={request.url} />,
        {
          [callbackName]: () => {
            const body = new PassThrough();
            const stream = createReadableStreamFromReadable(body);
            responseHeaders.set("Content-Type", "text/html");
            resolve(new Response(stream, { headers: responseHeaders, status: responseStatusCode }));
            pipe(body);
          },
          onShellError(error) {
            reject(error);
          },
          onError(error) {
            responseStatusCode = 500;
            logError("ui.render.failed", error);
          },
        },
      );
      setTimeout(abort, streamTimeout + 1000);
    });
  });
}
