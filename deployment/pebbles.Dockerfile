# Use official Python image
FROM docker.io/library/python:3.12
LABEL "io.k8s.display-name"="pebbles"
ARG EXTRA_PIP_PACKAGES
ARG PB_APP_VERSION="not-set"

# display app version in build logs
RUN echo "PB_APP_VERSION: $PB_APP_VERSION"

USER root

# Add inotify for gunicorn hot reload
RUN apt-get update && apt-get install -y inotify-tools && apt-get clean

# Use s2i compatible workdir
WORKDIR /opt/app-root/src

# Install requirements from requirements.txt and build argument
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
RUN if [ -n "$EXTRA_PIP_PACKAGES" ]; then pip install --no-cache-dir $EXTRA_PIP_PACKAGES; fi

# Pick the required bits of source code
COPY manage.py .
COPY migrations ./migrations
RUN mkdir deployment
COPY deployment/run_gunicorn.bash deployment/.
RUN chmod 755 deployment/run_gunicorn.bash
COPY pebbles ./pebbles
COPY tests ./tests

# stamp with given application version
RUN echo "{\"appVersion\": \"$PB_APP_VERSION\"}" > app-version.json

CMD ["./deployment/run_gunicorn.bash"]
