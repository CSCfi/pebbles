# DockerDriver

## Getting started

After following the standard install instructions the following additional steps
are required to activate docker driver:

### Pull a docker image

At the time of writing, docker driver will upload images to new notebook hosts (instead of hosts pulling them
from a private Docker registry). The images will need to be downloaded (from dockerhub) and placed in server's 
/var/lib/pb/docker_images -directory:

As cloud-user on the server, pull the images:
    
    docker pull rocker/rstudio

Then save the image to image directory (/var/lib/pb/docker_images by default):

    docker save rocker/rstudio | gzip -c > /var/lib/pb/docker_images/rocker.rstudio.img

NOTE: Images from the image directory are pushed to notebook hosts only when they are being
      prepared. This limitation will be removed in the future, see
      https://github.com/CSC-IT-Center-for-Science/pouta-blueprints/issues/358

### Configure the driver

Change the following configuration variables in the web configuration page visible for admins.

    PLUGIN_WHITELIST: DockerDriver
    DD_SHUTDOWN_MODE: False

Once you enable the driver, you can take a look at the tmux status window mentioned in how_to_install_on_cpouta.md, 
window number 2 (CTRL-b 2) how the provisioning of notebook hosts in the pool is coming along.

### Open port 8443 in your security group

The notebook connections from clients to the backing docker containers are proxied through port 8443 on the server. 
Make sure that is open to the networks you want to expose the system to.

## Create a test blueprint

Go to Web UI, select 'Configure' tab, click on 'Create Blueprint' next to DockerDriver

Settings:

* Name: docker-rstudio-10m
* Description: Rocker RStudio image, use rstudio/rstudio as credentials
* docker_image: rocker/rstudio
* Internal port: 8787
* Maximum lifetime: 10m

Save and activate, go to 'Dashboard' and launch an instance. Once the instance is running, click 'Open in Browser'

## Shutting down the server

Because DockerDriver maintains a pool of VMs to host the containers, you will have to shut it down in an orderly
fashion for all the allocated resources to be deleted/released. Before shutting down the main server, simply set
 
    DD_SHUTDOWN_MODE: True
    
and the driver will delete the resources in the pool. In case there is an runaway container and the hosts are not
empty, you will have to manually delete the VM, security group and volume from OpenStack.
