# jfin2etv runtime image (DESIGN.md §3.1, §16.2)
FROM python:3.12-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
        ruby ruby-dev build-essential ffmpeg tini ca-certificates tzdata curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

COPY pyproject.toml uv.lock* README.md ./
COPY src/ ./src/
RUN uv sync --frozen --no-dev || uv sync --no-dev

COPY lib/ ./lib/
COPY vendor/ ./vendor/
COPY Gemfile Gemfile.lock* ./
RUN gem install bundler --no-document \
    && bundle config set --local deployment 'true' \
    && bundle config set --local without 'development test' \
    && bundle install || bundle install --no-deployment

RUN groupadd --system --gid 1000 jfin2etv \
    && useradd --system --uid 1000 --gid jfin2etv --home-dir /app --shell /usr/sbin/nologin jfin2etv \
    && mkdir -p /config /scripts /state /epg /ersatztv-config \
    && chown -R jfin2etv:jfin2etv /app /config /scripts /state /epg /ersatztv-config

USER jfin2etv

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:${PATH}" \
    BUNDLE_PATH=/app/vendor/bundle

EXPOSE 8080

HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8080/healthz || exit 1

ENTRYPOINT ["tini", "--", "jfin2etv"]
CMD ["run"]
