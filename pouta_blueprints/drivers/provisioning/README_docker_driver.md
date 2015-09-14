# DockerDriver

## Things to do to get the early hack up and running:

- set up a docker host on cPouta
    - add -H tcp://0.0.0.0:2375 to the config in either /etc/defaults/docker (Ubuntu) or /etc/sysconfig/docker (CentOS 7)
- set up an ssh tunnel from worker port 12375 to the docker host port 2375
- change the public IP in docker_driver.DockerDriver._get_hosts() to match the public ip on your docker host

## Todo:

### Essentials
- add periodical plugin calls to tasks for housekeeping *DONE* 
- setup openstack ssh-key *DONE*

- docker host spawning *DONE*
    - TBD: Where is host config stored? In app config *DONE*
    - TBD: Is there a host config per blueprint? This would mean a host pool per blueprint. Nope. *DONE*

- docker host configuration ansible playbooks *DONE*
- security group configuration *DONE*
- trigger automatic host configuration *DONE*

- set up secure PB to docker host comms *DONE*
    - https://docs.docker.com/articles/https/

- create a resource pool *DONE*

- add more states for hosts in pool *DONE*
    - spawned
    - prepared *REJECTED*
    - active
    - inactive
    - removed

- implement host selection *DONE*

- periodical tasks
    - implement spawn host *DONE*
    - implement remove host *DONE*

- get rid of hard coded configuration *DONE*  
    - image, flavor, security groups, docker image, number of instances per host,... *DONE*  
    - blueprint config, (pool of hosts per blueprint)
    - OR a commmon configuration for the hosts, stored in the file system?
    - OR a common config, but just use variables *DONE* 
       
- setting password for containers *OBSOLETED by proxy* 
    - rstudio *DONE*
    - jupyter

- proxy in front of containers *DONE, with nginx*
    - spawn a third container 
    - install configurable-http-proxy from jupyter project 
    - setup keys for API
    - add hooks to provisioning/deprovisioning/housekeeping to add/remove forwarded ports
    - add the proxy hash path to the instance URL, get rid of the password

- add ssl termination to the proxy
    
- implement memory limits for containers 
  - pending for docker-py update https://github.com/docker/docker-py/pull/732
  
- implement error tracking per host *DONE*
    - prevent a bad host from stalling the pool 

- make jupyter/minimal containers work
    - need to modify the command string
    - substitute a base url parameter with the generated route_id 

### Optional features
- implement session backups
- implement a service for plugins for storing the state 
- configure swap on host + allow swapping for containers for fitting even more on a single host?
