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

* Upload public key or create a key pair, if you have not done so already ()

## Create a security group for the server

* In case you are a member of multiple projects in cPouta, select the desired project in the project selection 
  drop down box on the top of the page 

* Create a security group called 'pb_server' for the server ('Access and Security'->'Create Security Group')

* Add ssh and https -access to your workstation IP/subnet (Manage rules -> Add rule) 
  * ssh: port 22, CIDR: your ip/32 (you can check your ip with e.g. http://www.whatismyip.com/)
  * https: port 443, CIDR: like above

## Boot the server

* Go to (Instances -> Launch Instance)

* Details tab:
  * Instance name: e.g. 'pb_server'
  * Flavor: mini
  * Instance boot source: boot from image, Image: Ubuntu-14.04

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

Open ssh connection to the server::

    $ ssh cloud-user@<public ip of the server>

Download the installation script from GitHub::

    $ wget  

    
