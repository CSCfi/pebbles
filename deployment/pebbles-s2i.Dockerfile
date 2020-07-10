# Created by s2i, modified to need
FROM centos/python-38-centos7
LABEL "io.k8s.display-name"="pebbles"
ENV UPGRADE_PIP_TO_LATEST="1"
USER root

# Copying in necessary bits of source code
RUN mkdir /tmp/src
COPY requirements.txt /tmp/src/requirements.txt
COPY manage.py /tmp/src/manage.py
COPY pebbles /tmp/src/pebbles
RUN mkdir /tmp/src/deployment
COPY deployment/run_gunicorn.bash /tmp/src/deployment

# Change file ownership to the assemble user. Builder image must support chown command.
RUN chown -R 1001:0 /tmp/src
USER 1001

# Assemble script sourced from builder image based on user input or image metadata.
# If this file does not exist in the image, the build will fail.
RUN /usr/libexec/s2i/assemble

# Run script sourced from builder image based on user input or image metadata.
# If this file does not exist in the image, the build will fail.
CMD /usr/libexec/s2i/run
