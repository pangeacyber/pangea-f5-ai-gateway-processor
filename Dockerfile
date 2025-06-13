FROM python:3.13-bookworm AS build

WORKDIR /build

RUN apt-get update && \
		apt-get install -y make cmake gcc g++ && \
		pip install uv
		# curl -LsSf https://astral.sh/uv/install.sh | sh

COPY README.md README.md
COPY pyproject.toml pyproject.toml
COPY ./src ./src
COPY uv.lock uv.lock

RUN uv sync --no-editable && \
		uv pip freeze > requirements.txt && \
		pip wheel --no-cache-dir --no-deps --wheel-dir ./wheels -r ./requirements.txt

FROM python:3.13-slim-bookworm
WORKDIR /app

RUN --mount=type=bind,from=build,source=/build/wheels,target=/app/wheels \
		--mount=type=bind,from=build,source=/build/requirements.txt,target=/app/requirements.txt \
		pip install --no-cache /build/wheels/*

# TODO: Entrypoint, or start script or something probably
CMD [ \
	"python", \
	"-m", \
	"uvicorn", \
	"--factory", \
	"pangea_f5_ai_gateway_processor.app:app", \
	"--host", \
	"0.0.0.0", \
	"--port", \
	"9999" \
]
