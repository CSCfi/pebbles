# DockerDriver

## Things to do to get the early hack up and running:

- set up a docker host on cPouta
    - add -H tcp://0.0.0.0:2375 to the config in either /etc/defaults/docker (Ubuntu) or /etc/sysconfig/docker (CentOS 7)
- set up an ssh tunnel from worker port 12375 to the docker host port 2375
- change the public IP in docker_driver.DockerDriver._get_hosts() to match the public ip on your docker host

## Todo:

### Essentials
- docker host spawning (OpenStack driver to the rescue?)
    - TBD: Where is host config stored?
    - TBD: Is there a host config per blueprint? This would mean a host pool per blueprint.
- docker host configuration with ansible
- setup openstack ssh-key (per host?)
- set up secure PB to docker host comms
    - https://docs.docker.com/articles/https/
- create a resource pool
- implement host selection
- periodical tasks
    - implement spawn host
    - implement remove host

### Done
- add periodical plugin calls to tasks for housekeeping 


### Optional features
- implement session backups
- proxy in front of containers
- implement a service for plugins for storing the state 

### Done
- 
