import { readFile } from "node:fs/promises";
import path from "node:path";

// The App Store listing's privacy policy and terms (public/legal/*.html), served
// at /privacy and /terms by the app itself, so they don't depend on the Caddy
// rewrite (deploy/caddy/Caddyfile.snippet) being pasted on the proxy.
export async function legalPage(name: "privacy" | "terms"): Promise<Response> {
  const file = path.join(process.cwd(), "public", "legal", `${name}.html`);
  const html = await readFile(file, "utf8");
  return new Response(html, {
    headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "public, max-age=3600" },
  });
}
