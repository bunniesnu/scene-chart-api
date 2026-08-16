FROM python:3.14-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates

ADD https://astral.sh/uv/install.sh /uv-installer.sh

RUN sh /uv-installer.sh && rm /uv-installer.sh

ENV PATH="/root/.local/bin/:$PATH"
ENV UV_PYTHON_DOWNLOAD=auto
ENV UV_PYTHON=3.14

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

ARG TARGETARCH

ENV SUPERCRONIC_VERSION=v0.2.49
ENV SUPERCRONIC_BASE_URL=https://github.com/aptible/supercronic/releases/download/${SUPERCRONIC_VERSION}

RUN set -eux; \
    case "${TARGETARCH}" in \
        amd64) \
            SUPERCRONIC_SHA1SUM="e63c11a9726b775a6a11801e81af4f3fb926aa68" \
            ;; \
        arm64) \
            SUPERCRONIC_SHA1SUM="0b6c5bb743e0b0dafed1132198c81807927ac413" \
            ;; \
        *) \
            echo "Unsupported architecture: ${TARGETARCH}" >&2 \
            exit 1 \
            ;; \
    esac; \
    SUPERCRONIC="supercronic-linux-${TARGETARCH}"; \
    curl -fsSLO "${SUPERCRONIC_BASE_URL}/${SUPERCRONIC}"; \
    echo "${SUPERCRONIC_SHA1SUM}  ${SUPERCRONIC}" | sha1sum -c -; \
    chmod +x "${SUPERCRONIC}"; \
    mv "${SUPERCRONIC}" "/usr/local/bin/${SUPERCRONIC}"; \
    ln -s "/usr/local/bin/${SUPERCRONIC}" /usr/local/bin/supercronic

COPY . .

EXPOSE 8000
