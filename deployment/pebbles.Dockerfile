# Use official Python image
FROM docker.io/library/python:3.11.5-bullseye
LABEL "io.k8s.display-name"="pebbles"
ARG EXTRA_PIP_PACKAGES

USER root

# Add inotify for gunicorn hot reload
RUN apt update && apt install -y inotify-tools && apt clean

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

CMD ["./deployment/run_gunicorn.bash"]
