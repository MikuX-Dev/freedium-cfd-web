FROM oven/bun:1.2-slim

WORKDIR /app

COPY package.json bun.lock* ./
RUN bun install --production

COPY server.ts ./

EXPOSE 8085

# Light: bun + zero-dep mdream. Healthcheck hits the in-process /healthz.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD bun -e "fetch('http://localhost:8085/healthz').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

CMD ["bun", "run", "server.ts"]
