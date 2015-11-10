FROM jupyter/datascience-notebook

MAINTAINER Olli Tourunen <olli.tourunen@csc.fi>
RUN conda install --yes \
    'bokeh'

COPY bootstrap_and_start.bash /usr/local/bin/
RUN chown root.root /usr/local/bin/bootstrap_and_start.bash
RUN chmod 755 /usr/local/bin/bootstrap_and_start.bash