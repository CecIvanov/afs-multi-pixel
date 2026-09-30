FROM node:22-alpine
RUN apk add --no-cache openssl

WORKDIR /app
EXPOSE 3000

COPY package.json package-lock.json ./
COPY extensions/multi-pixel-checkout/package.json extensions/multi-pixel-checkout/package.json
RUN npm install --no-audit --no-fund

COPY . .
RUN npx prisma generate && npm run build && npm prune --omit=dev

ENV NODE_ENV=production
# DATABASE_URL points at the mounted volume (see docker-compose.yml); migrations run on start.
CMD ["npm", "run", "docker-start"]
