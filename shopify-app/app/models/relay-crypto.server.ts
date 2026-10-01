import prisma from "../db.server";

// Envelope sent by the storefront: the event JSON is encrypted with a fresh AES-256-GCM key, and that
// key is encrypted with the app's RSA-OAEP (SHA-256) public key. Only this server can read it.
export type Envelope = { v: 1; k: string; iv: string; d: string };

const { subtle } = globalThis.crypto;
const RSA = { name: "RSA-OAEP", hash: "SHA-256" } as const;

const toB64 = (buffer: ArrayBuffer) => Buffer.from(buffer).toString("base64");
const fromB64 = (value: string) => new Uint8Array(Buffer.from(value, "base64"));

let cachedPrivateKey: CryptoKey | null = null;

// The key pair is generated once and kept in SQLite (the Docker volume). The public half is
// published to the theme embed and the Web Pixel when the Pixel Mapping is saved.
export async function getPublicKey(): Promise<string> {
  const existing = await prisma.appKey.findUnique({ where: { id: 1 } });
  if (existing) return existing.publicKey;

  const pair = await subtle.generateKey(
    { ...RSA, modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]) },
    true,
    ["encrypt", "decrypt"],
  );
  const publicKey = toB64(await subtle.exportKey("spki", pair.publicKey));
  const privateKey = toB64(await subtle.exportKey("pkcs8", pair.privateKey));
  const saved = await prisma.appKey.upsert({
    where: { id: 1 },
    create: { id: 1, publicKey, privateKey },
    update: {},
  });
  return saved.publicKey;
}

async function privateKey(): Promise<CryptoKey> {
  if (cachedPrivateKey) return cachedPrivateKey;
  const key = await prisma.appKey.findUnique({ where: { id: 1 } });
  if (!key) throw new Error("No relay key pair yet; save the Pixel Mapping once");
  cachedPrivateKey = await subtle.importKey("pkcs8", fromB64(key.privateKey), RSA, false, ["decrypt"]);
  return cachedPrivateKey;
}

export async function decryptEnvelope(raw: string): Promise<unknown> {
  const envelope = JSON.parse(raw) as Envelope;
  if (envelope.v !== 1 || !envelope.k || !envelope.iv || !envelope.d) {
    throw new Error("Malformed envelope");
  }
  const aesRaw = await subtle.decrypt(RSA, await privateKey(), fromB64(envelope.k));
  const aesKey = await subtle.importKey("raw", aesRaw, "AES-GCM", false, ["decrypt"]);
  const plain = await subtle.decrypt(
    { name: "AES-GCM", iv: fromB64(envelope.iv) },
    aesKey,
    fromB64(envelope.d),
  );
  return JSON.parse(new TextDecoder().decode(plain));
}
