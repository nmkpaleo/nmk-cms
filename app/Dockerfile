FROM python:3.10-slim@sha256:c1aaf3d03e14944a039a1647e0b3f6f34c6bee517bac6ff380215ee099c4e808 AS compile-image

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && \
    apt-get install -y build-essential gcc default-libmysqlclient-dev && \
    useradd -m user

USER user

COPY requirements-ci.lock .
RUN python -m pip install --require-hashes -r requirements-ci.lock

# Tooth-marking inference is enabled in production and uses the CPU-only,
# hash-verified dependency set. Installing it in the compile stage makes the
# packages available in the final image via the copied user site-packages.
COPY requirements-tooth-marking-cpu.lock .
RUN python -m pip install --require-hashes -r requirements-tooth-marking-cpu.lock

# ---------------------------------

FROM python:3.10-slim@sha256:c1aaf3d03e14944a039a1647e0b3f6f34c6bee517bac6ff380215ee099c4e808 AS torch-cpu-compat-check

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

ARG TORCH_CPU_VERSION=2.8.0+cpu
ARG TORCHVISION_CPU_VERSION=0.23.0+cpu

# TM-001 feasibility gate (optional target):
#   docker build --target torch-cpu-compat-check app/
# Verifies Python 3.10 compatibility and CPU wheel availability from PyTorch index.
RUN python -m pip download \
      --extra-index-url https://download.pytorch.org/whl/cpu \
      --only-binary=:all: \
      "torch==${TORCH_CPU_VERSION}" \
      "torchvision==${TORCHVISION_CPU_VERSION}"

# ---------------------------------

FROM python:3.10-slim@sha256:c1aaf3d03e14944a039a1647e0b3f6f34c6bee517bac6ff380215ee099c4e808 AS build-image

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}

WORKDIR /src/app

RUN apt-get update && \
    apt-get install -y default-libmysqlclient-dev && \
    useradd -m user && \
    mkdir -p /vol/web/static && \
    mkdir -p /vol/web/media && \
    chown -R user:user /vol && \
    chmod -R 755 /vol/web

USER user

COPY --from=compile-image /home/user/.local /home/user/.local

ENV PATH=/home/user/.local/bin:$PATH

COPY . .

CMD ["sh", "./scripts/entrypoint.sh"]
