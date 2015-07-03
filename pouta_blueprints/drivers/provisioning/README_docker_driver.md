# DockerDriver

Things to do to get the early hack up and running:

- set up a docker host on cPouta
  - add -H tcp://0.0.0.0:2375 to the config in either /etc/defaults/docker (Ubuntu) or /etc/sysconfig/docker (CentOS 7)
- set up an ssh tunnel from worker port 12375 to the docker host port 2375
- change the public IP in docker_driver.DockerDriver._get_hosts() to match the public ip on your docker host




  