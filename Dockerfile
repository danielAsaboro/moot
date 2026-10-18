# Stage 1: build the Next.js UI to static files (frontend/out). Node is only needed here.
FROM node:22-slim AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-fund --no-audit
COPY frontend/ ./
RUN NEXT_TELEMETRY_DISABLED=1 npm run build

# Stage 2: the Python app, which serves the API and the built UI from one port.
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY moot ./moot
COPY web ./web
COPY data ./data
COPY eval ./eval
COPY --from=ui /ui/out ./frontend/out
RUN pip install --no-cache-dir . && pip install --no-cache-dir falkordblite
ENV PORT=8000
EXPOSE 8000
# Seeds the graph on every start (idempotent MERGE), then serves.
CMD ["sh", "-c", "python -m moot.cli seed && python -m moot.cli serve --port ${PORT}"]
