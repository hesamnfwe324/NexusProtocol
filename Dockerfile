FROM node:20-alpine AS builder
WORKDIR /app

RUN npm install -g pnpm@10

COPY pnpm-workspace.yaml pnpm-lock.yaml package.json ./
COPY lib/ ./lib/
COPY artifacts/api-server/ ./artifacts/api-server/

# Disable minimumReleaseAge so pnpm install works on build servers
RUN sed -i 's/minimumReleaseAge: 1440/minimumReleaseAge: 0/' pnpm-workspace.yaml

RUN pnpm install --no-frozen-lockfile
RUN pnpm --filter @workspace/api-server run build

FROM node:20-alpine
WORKDIR /app

COPY --from=builder /app/artifacts/api-server/dist ./dist
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/artifacts/api-server/node_modules ./artifacts/api-server/node_modules

ENV PORT=8080
EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=5s --retries=5 \
  CMD wget -qO- http://localhost:8080/api/healthz || exit 1

CMD ["node", "--enable-source-maps", "dist/index.mjs"]

