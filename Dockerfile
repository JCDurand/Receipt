FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# A fixed version, so that a rebuild cannot pick up a different uv
COPY --from=ghcr.io/astral-sh/uv:0.13.0 /uv /uvx /bin/

RUN apt-get update && apt-get install -y tesseract-ocr ghostscript curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN uv pip install -r requirements.txt --system

# Django runs as this user instead of root. Its id is the id of the host user
# who starts the stack (the startup scripts write APP_UID to .env), because the
# files in secrets/ and the folders mounted from the host belong to that user.
ARG APP_UID=1000
RUN useradd --uid "$APP_UID" --user-group --create-home --shell /usr/sbin/nologin app

COPY . .

# The code stays owned by root, so the app cannot change it. These are the only
# folders it writes to: uploaded documents and the parsers' working files.
RUN mkdir -p document_storage tmp text_layered \
    && chown app:app document_storage tmp text_layered

USER app

EXPOSE 8000

ENTRYPOINT [ "/bin/bash","entrypoint.sh" ]
