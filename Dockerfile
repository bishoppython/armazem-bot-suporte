FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.9.5 /uv /bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY empresas ./empresas
COPY avaliacao ./avaliacao
RUN uv sync --frozen --no-dev
RUN useradd --create-home bot && mkdir -p dados && chown bot dados
USER bot
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/saude')"
CMD ["uv", "run", "--no-sync", "bot", "servir", "--host", "0.0.0.0"]
