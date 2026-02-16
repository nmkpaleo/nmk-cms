FROM python:3.10-slim AS compile-image

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && \
    apt-get install -y build-essential gcc default-libmysqlclient-dev && \
    useradd -m user

USER user

COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --user -r requirements.txt

# ---------------------------------

FROM python:3.10-slim AS torch-cpu-compat-check

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

ARG TORCH_CPU_VERSION=2.8.0+cpu
ARG TORCHVISION_CPU_VERSION=0.23.0+cpu

# TM-001 feasibility gate (optional target):
#   docker build --target torch-cpu-compat-check app/
# Verifies Python 3.10 compatibility and CPU wheel availability from PyTorch index.
RUN python -m pip install --upgrade pip && \
    python -m pip download \
      --extra-index-url https://download.pytorch.org/whl/cpu \
      --only-binary=:all: \
      "torch==${TORCH_CPU_VERSION}" \
      "torchvision==${TORCHVISION_CPU_VERSION}"

# ---------------------------------

FROM python:3.10-slim AS build-image

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

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
