# DockerDriver

## Getting started

After following the standard install instructions the following additional steps
are required to activate docker driver:

### Pull the docker images

At the time of writing, docker driver will try to upload two images to new notebook hosts. The images
will need to be downloaded from dockerhub and placed in worker's /images -directory:

As cloud-user on the server, pull the images
    
    docker pull rocker/rstudio
    docker pull rocker/ropensci

Then save the images to image directory (/var/lib/pb/docker_images by default)

    docker save rocker/rstudio | gzip -c > /var/lib/pb/docker_images/rocker.rstudio.img
    docker save rocker/ropensci | gzip -c > /var/lib/pb/docker_images/rocker.ropensci.img

NOTE: Images from the image directory are pushed to notebook hosts only when they are being
      prepared. This limitation will be removed in the future, see
      https://github.com/CSC-IT-Center-for-Science/pouta-blueprints/issues/358
       

### Configure the driver

Change the following configuration variables in the web configuration page visible for admins.

    PLUGIN_WHITELIST DockerDriver
    DD_SHUTDOWN_MODE False

### Open port 8443 in your security group

The notebook connections from clients to the backing docker containers are proxied
through port 8443 on the server. Make sure that is open to the networks you want to
expose the system to.
