FROM node:22-slim AS frontend

WORKDIR /src/app

COPY app/package.json app/package-lock.json ./
RUN npm ci

COPY app/ ./
# the webpack output goes to ../kube_ops_view/static/build (i.e. /src/kube_ops_view/static/build)
RUN npm run build

FROM python:3.13-slim AS backend

WORKDIR /

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock /
RUN UV_PROJECT_ENVIRONMENT=/opt/venv uv sync --frozen --no-dev --no-install-project

FROM python:3.13-slim

WORKDIR /

# copy pre-built packages to this image
COPY --from=backend /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# now copy the actual code we will execute (uv sync above was just for dependencies)
COPY kube_ops_view /kube_ops_view
COPY --from=frontend /src/kube_ops_view/static/build /kube_ops_view/static/build

ARG VERSION=dev

RUN sed -i "s/__version__ = .*/__version__ = '${VERSION}'/" /kube_ops_view/__init__.py

ENTRYPOINT ["python3", "-m", "kube_ops_view"]
