FROM nginx:alpine@sha256:df221db836e1754089190208cee7eeda94f233197056426eda74a43ab1abeac2

COPY ./default.conf /etc/nginx/templates/default.conf.template
COPY ./certs /certs

RUN mkdir -p /vol/static && \
    chmod 755 /vol/static && \
    mkdir -p /vol/media && \
    chmod 755 /vol/media