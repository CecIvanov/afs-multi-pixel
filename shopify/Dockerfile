# React Router v7 embedded Shopify app. Build context is the repository ROOT so
# the shared packages/logger can be copied into the monorepo layout the app imports.
# The base image is pinned by digest (Node 22.23.3) and installs use `npm ci`, so a
# rebuild on the VPS gets exactly what was tested (as BG Delivery does).
FROM node:22-alpine@sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402 AS build
RUN apk add --no-cache openssl
WORKDIR /workspace

# Shared package (app imports ../../packages/logger).
COPY packages/logger ./packages/logger

COPY shopify/package.json shopify/package-lock.json* ./shopify/
# npm workspaces (the extensions) must be present for the lockfile install.
COPY shopify/extensions/multi-pixel-checkout/package.json ./shopify/extensions/multi-pixel-checkout/
WORKDIR /workspace/shopify
RUN npm ci

COPY shopify/ .
RUN npx prisma generate && npm run build

FROM node:22-alpine@sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402
RUN apk add --no-cache openssl wget
ENV NODE_ENV=production
WORKDIR /app

# packages/logger is bundled into build/ at compile time, so the runtime image
# only needs the app's own production deps.
COPY shopify/package.json shopify/package-lock.json* ./
COPY shopify/extensions/multi-pixel-checkout/package.json ./extensions/multi-pixel-checkout/
RUN npm ci --omit=dev && npm cache clean --force

COPY --from=build /workspace/shopify/build ./build
COPY --from=build /workspace/shopify/public ./public
COPY --from=build /workspace/shopify/prisma ./prisma
COPY --from=build /workspace/shopify/scripts ./scripts
COPY --from=build /workspace/shopify/node_modules/.prisma ./node_modules/.prisma

EXPOSE 3000
CMD ["npm", "run", "docker-start"]
