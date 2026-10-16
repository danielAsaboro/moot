FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY moot ./moot
COPY web ./web
COPY data ./data
COPY eval ./eval
RUN pip install --no-cache-dir . && pip install --no-cache-dir falkordblite
ENV PORT=8000
EXPOSE 8000
# Seeds the graph on every start (idempotent MERGE), then serves.
CMD ["sh", "-c", "python -m moot.cli seed && python -m moot.cli serve --port ${PORT}"]
