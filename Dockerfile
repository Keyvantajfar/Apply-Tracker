FROM python:3.12-slim AS build
WORKDIR /src
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip wheel --no-cache-dir --wheel-dir /wheels .

FROM python:3.12-slim
LABEL org.opencontainers.image.title="GradApp" \
      org.opencontainers.image.source="https://github.com/OWNER/gradapp"
RUN useradd --create-home --uid 10001 gradapp
COPY --from=build /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels
ENV GRADAPP_DATA=/data GRADAPP_HOST=0.0.0.0 GRADAPP_PORT=5000
RUN mkdir /data && chown gradapp /data
USER gradapp
VOLUME /data
EXPOSE 5000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request,os;urllib.request.urlopen('http://127.0.0.1:%s/healthz'%os.environ['GRADAPP_PORT'])" || exit 1
CMD ["gradapp", "serve"]
