# How to launch Pouta Blueprints server on cPouta

These are step by step instructions on how to launch a Pouta Blueprints server on 
cPouta IaaS cloud (https://research.csc.fi/pouta-iaas-cloud). We assume that you are
familiar with the cPouta service. Horizon web interface will be used as an example.

First we create a security group, then launch a server and finally install the software
using ssh interactive session.

# Part 1: Launch the server

## Prerequisites

* First log in to https://pouta.csc.fi

* Check that quota on the first page looks ok.

* Upload public key or create a key pair, if you have not done so already (Access and Security -> Key Pairs)

## Create a security group for the server

* In case you are a member of multiple projects in cPouta, select the desired project in the project selection 
  drop down box on the top of the page 

* Create a security group called 'pb_server' for the server (Access and Security -> Create Security Group)

* Add ssh and https -access to your workstation IP/subnet (Manage rules -> Add rule) 
  * ssh: port 22, CIDR: your ip/32 (you can check your ip with e.g. http://www.whatismyip.com/)
  * https: port 443, CIDR: like above

* At this point keep the firewall as restricted as possible. Once the installation is complete, you can open the
 https-access to all your users.

## Boot the server

We'll next create the server VM. It will be based on CentOS-7.0, and use an OpenStack volume as the root disk
to gain more space, speed and resilience against single disk failures.

* Go to (Instances -> Launch Instance)

* Details tab:
  * Instance name: e.g. 'pb_server'
  * Flavor: mini
  * Instance boot source: boot from image (creates new volume)
  * Image: CentOS-7.0
  * Device size: 20 GB

* Access and security tab:
  * Key Pair: your keypair
  * Security Groups: unselect 'default', select 'pb_server'

* Networks tab: default network is ok.

* Post-Creation and Advanced tabs can be skipped

## Assign a public IP

* Go to (Instances) and click More on pb_server instance row. Select 'Associate floating IP'

* Select a free floating IP from the list and click 'Associate' 

* If there are no items in the list, allocate an address with (+). 
 

## Download machine to machine OpenStack RC -file

* Log out and log in to https://pouta.csc.fi again, this time using your machine to machine credentials

* Go to (Access and Security -> API Access) and click 'Download OpenStack RC File'. Save the file to a known location
  on your local computer
  
# Part 2: Install software

Open ssh connection to the server:

    $ ssh cloud-user@<public ip of the server>

Update the server packages (we'll boot it later):

    $ sudo yum update -y
    
Clone the repository from GitHub:

    $ sudo yum install -y git
    $ git clone --branch v2.0.0 https://github.com/CSC-IT-Center-for-Science/pouta-blueprints.git

Run the install script once - you will asked to log out and in again to make unix group changes effective. Here is a 
good time to reboot the server after the updates:

    $ ./pouta-blueprints/scripts/install_pb.bash
    $ sudo reboot

Wait while for the server to reboot and copy the m2m OpenStack RC file to the server:

    $ scp path/to/your/saved/rc-file.bash cloud-user@<public ip of the server>:

SSH in again, source your m2m OpenStack credentials (use your m2m password when asked for) and continue installation:

    $ ssh cloud-user@<public ip of the server>
    $ source your-openrc.bash
    $ ./pouta-blueprints/scripts/install_pb.bash

    
Running nano/vim in each of the containers:

    ssh www
    sudo vim /etc/pouta_blueprints/config.yaml.local
    exit
    
    ssh worker
    sudo vim /etc/pouta_blueprints/config.yaml.local 
    exit

# Part 3: Quick start using the software

Here is list of tasks for a quick start. 

Link to more comprehensive Admin Guide: TBA

## Set admin credentials

The installation script will print out initialization URL at the end of the installation. Navigate to that, set the
admin credentials and log in as an admin.

## Configure mail

To configure the outgoing mail settings, go to Configure tab, and change the following:

    SENDER_EMAIL: 'your.valid.email@example.org'
    MAIL_SERVER: 'server.assigned.to.you.by.csc'
    MAIL_SUPPRESS_SEND: False

## Enable OpenStack Driver

By default, only a dummy test driver is enabled. To add more drivers for provisioning different resources, you need 
to edit the _PLUGIN_WHITELIST_ variable. Change DummyDriver to OpenStackDriver:

    PLUGIN_WHITELIST: OpenStackDriver

The plugin infrastructure running in 'worker' container will periodically check the plugin whitelist
and upload driver configurations to the API/www server running in 'www' container. In the case of OpenStackDriver,
the configuration will dynamically include VM images and flavors that are available for the cPouta project. 
Refresh the page after a minute or two, and the *Plugins* list on top of the page should include OpenStackDriver

## Create a test blueprint

Click 'Create Blueprint' next to OpenStackDriver in the plugin list and you are presented by a dialog for configuring 
the new blueprint. We'll create a blueprint for Ubuntu-14.04 based VM, using mini flavor, running for 1h maximum. We'll
also test running a custom command as part of the boot process and allow user to open ssh access to the instance from 
an arbitrary address
 
* Name: Ubuntu-14.04 test
* Description: Test blueprint for launching a single core Ubuntu-14.04 VM in cPouta
* Flavor: mini
* Maximum lifetime: 1h
* Maximum instances per user: 1
* Pre-allocate credits for the instance from the user quota: unchecked
* Cost multiplier: 0
* Remove the example Frontend firewall rule
* Allow user to request instance firewall to allow access to user's IP address: check

Also add a Customization script, just for test purposes:

    #!/bin/bash
    touch /tmp/hello_from_blueprint_config

Save the new blueprint and enable it in the Blueprints list.

## Launch a test instance

Go to 'Dashboard' tab. If you have not uploaded your ssh public key yet, you'll see a notice with a link to do so
in the Blueprint list. Click the link and upload or generate a public key.

Go back to 'Dashboard' and launch an instance. You'll notice the new instance in the Instance list. Click on the 
instance name, that will take you to the detailed view, where you can see the provisioning logs and update access to
your IP once the instance is up and running. Click on 'Query client IP' to let the system take an educated guess 
of your IP and then 'Change client IP'. Now the instance firewall is open to that given IP. Copy the ssh -command from 
the Access field above and paste that to a terminal (or an ssh-client):

    $ ssh cloud-user@86.50.xxx.xxx

Check if our boot time customization script worked:

    $ ls -l /tmp/hello_from_blueprint_config 
    -rw-r--r-- 1 root root 0 Nov 17 09:47 /tmp/hello_from_blueprint_config


## Enable Docker Driver

Enabling DockerDriver requires a bit more preparation, see [DockerDriver readme](https://github.com/CSC-IT-Center-for-Science/pouta-blueprints/blob/master/pouta_blueprints/drivers/provisioning/README_docker_driver.md)

# Part 4: Open access to users

Once you have set the admin credentials and checked that the system works, you can open the firewall to all the users. 

* Go to pouta.csc.fi -> Access and Security -> Security Groups and select Manage Rules on 'pb_server' group  

* Open https -access either globally by selecting 'Add rule' -> port 443, CIDR 0.0.0.0/0 or if the users of the system 
  should always access it from a certain subnet, use that instead of 0.0.0.0/0

# Part 5: Administrative tasks and troubleshooting

(backing up the central database, cleaning misbehaving VMs and other resources, ...)

TBA 

# Notes on container based deployment

The default installation with the provided script makes a Docker container based deployment. Since the system will have
OpenStack credentials for the project it is serving and also be exposed to internet, we want to have an extra layer of 
isolation between http server and provisioning processes holding the credentials. The processes are not containerized 
more than necessary to achieve this, so you can think of the containers as mini virtual machines. In the future we are 
planning to make the containerization much more fine grained.

There are three containers, www, worker and proxy. You can list the status with:

    $ docker ps
    $ docker ps -a
    
Aliases are provided for an easy ssh access:

    $ ssh worker
    $ ssh www
    $ ssh proxy
    
Both of the containers share the git repository that was checked out during installation through a read only shared 
folder. Worker also has an additional shared folder for the credentials stored on the ramdisk on the host machine.

To see the server process logs, take a look at /webapps/pouta_blueprints/logs -directory in the container:

    $ ssh www
    $ ls /webapps/pouta_blueprints/logs

You can also launch a tmux based status session, that will have windows open for the host and each of the containers 
and multiple panes showing status and logs in each window:
    
    $ pouta-blueprints/scripts/tmux_status.bash
    
Tmux is terminal multiplexer like screen. Here is a quick survival guide:

Action              | Command
--------------------|--------------------
navigate the views  | CTRL-b + n
change active pane  | CTRL-b + arrow keys
exit/detach         | CTRL-b + d
new window          | CTRL-b + c
attach              | $ tmux attach (or att)
list sessions       | $ tmux list-sessions
kill a session      | $ tmux kill-session -t status
