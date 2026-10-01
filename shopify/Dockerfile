# React Router v7 embedded Shopify app. Build context is the repository ROOT so
# the shared packages/logger can be copied into the monorepo layout the app imports.
FROM node:22-alpine AS build
RUN apk add --no-cache openssl
WORKDIR /workspace

# Shared package (app imports ../../packages/logger).
COPY packages/logger ./packages/logger

COPY shopify/package.json shopify/package-lock.json* ./shopify/
# npm workspaces (the extensions) must be present for the lockfile install.
COPY shopify/extensions/multi-pixel-checkout/package.json ./shopify/extensions/multi-pixel-checkout/
WORKDIR /workspace/shopify
RUN npm install

COPY shopify/ .
RUN npx prisma generate && npm run build

FROM node:22-alpine
RUN apk add --no-cache openssl wget
ENV NODE_ENV=production
WORKDIR /app

# packages/logger is bundled into build/ at compile time, so the runtime image
# only needs the app's own production deps.
COPY shopify/package.json shopify/package-lock.json* ./
COPY shopify/extensions/multi-pixel-checkout/package.json ./extensions/multi-pixel-checkout/
RUN npm install --omit=dev && npm cache clean --force

COPY --from=build /workspace/shopify/build ./build
COPY --from=build /workspace/shopify/public ./public
COPY --from=build /workspace/shopify/prisma ./prisma
COPY --from=build /workspace/shopify/scripts ./scripts
COPY --from=build /workspace/shopify/node_modules/.prisma ./node_modules/.prisma

EXPOSE 3000
CMD ["npm", "run", "docker-start"]
