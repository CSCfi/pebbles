# DockerDriver

## Getting started

After following the standard install instructions the following additional steps
are required to activate docker driver:

### Pull the docker images

At the time of writing, docker driver will try to upload two images to new notebook hosts. The images
will need to be downloaded from dockerhub and placed in worker's /images -directory:

As cloud-user@server on the server, pull the images
    
    docker pull rocker/rstudio
    docker pull rocker/ropensci

Then stream the images to worker:/images/ over ssh

    docker save rocker/rstudio | ssh worker sudo dd of=/images/rocker.rstudio.img
    docker save rocker/ropensci | ssh worker sudo dd of=/images/rocker.ropensci.img

### Configure the driver

Change the following configuration variables in the web configuration page visible for admins.

    PLUGIN_WHITELIST DockerDriver
    DD_SHUTDOWN_MODE False
    

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
