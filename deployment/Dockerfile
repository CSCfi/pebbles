# based on an example by Anatoly Bubenkov "bubenkoff@gmail.com"

FROM ubuntu:14.04
MAINTAINER Olli Tourunen "olli.tourunen@csc.fi"

RUN apt-get update

RUN apt-get install -y openssh-server sudo

EXPOSE 22

RUN mkdir -p /var/run/sshd
RUN chmod 0755 /var/run/sshd

# Create and configure vagrant user
RUN useradd --create-home -s /bin/bash vagrant
WORKDIR /home/vagrant

# Configure SSH access
RUN mkdir -p /home/vagrant/.ssh
RUN echo "ssh-rsa AAAAB3NzaC1yc2EAAAABIwAAAQEA6NF8iallvQVp22WDkTkyrtvp9eWW6A8YVr+kz4TjGYe7gHzIw+niNltGEFHzD8+v1I2YJ6oXevct1YeS0o9HZyN1Q9qgCgzUFtdOKLv6IedplqoPkcmF0aYet2PkEDo3MlTBckFXPITAMzF8dJSIFo9D8HfdOV0IAdx4O7PtixWKn5y2hMNG0zQPyUecp4pzC6kivAIhyfHilFR61RGL+GPXQ2MWZWFYbAGjyiYJnAmCP3NOTd0jMZEnDkbUvxhMmBYSdETk1rRgm+R4LOzFUGaHqHDLKLX+FIPKcF96hrucXzcWyLbIbEgE98OHlnVYCzRdK8jlqm8tehUc9c9WhQ== vagrant insecure public key" > /home/vagrant/.ssh/authorized_keys
RUN chown -R vagrant: /home/vagrant/.ssh
RUN echo -n 'vagrant:vagrant' | chpasswd

# Enable passwordless sudo for the "vagrant" user
RUN echo 'vagrant ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/vagrant

# faster deployment with packages pre-installed in the base image
RUN apt-get install -y git python python-pip python-dev python-virtualenv supervisor redis-server \
                       libffi-dev libssl-dev python-yaml libffi-dev libssl-dev lsb-release

# fixed ansible version for consistency
RUN pip install "ansible==1.9.4"

# tools for admistration
RUN apt-get install -y tmux tree dstat lsof bash-completion time vim nano

COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf
RUN mkdir -p /var/log/supervisor

RUN ln -sf /vagrant /shared_folder


CMD ["/usr/bin/supervisord"]

