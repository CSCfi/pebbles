cPouta virtual machines in Pebbles
**********************************

These instructions show you how to create a cPouta image and use it to create OpenStackDriver Templates 
in a Pebbles installation. We assume that you are
familiar with the cPouta service and you login as an admin to the Pebbles UI. Horizon web interface will be used as an example.

OpenStackDriver can launch cPouta virtual machines from images existing in the installation's 
cPouta environment. There might be a number of basic images with preinstalled OS, these are easier to use in Pebbles. 
You may also customized virtual machines within cPouta (not covered here) and then create your own images. 
Custom images must be created as described below for them to be compatible with Pebbles.

Using an existing cPouta image
==============================
Make sure that your Pebbles installation has the OpenStackDriver configured
(`see the Admin guide instructions <http://cscfi.github.io/pebbles/admin_guide.html>`_).

We will create an OpenStackDriver template from an existing ´CentOS-7´ image. 
In Pebbles web UI go to ´Configure´ tab, and click on ´Create Template´ next to OpenStackDriver.

Settings:

* Name: centos-7-vm
* Description: CentOS 7 basic virtual machine
* Flavor: standard.tiny
* Image: CentOS-07
* Maximum lifetime: 10m
* Leave the rest as defaults
* TODO: review and add rest of parameters?
* TODO: review how security rules are set by Pebbles, currently not working properly (quick fix, set manually in cPouta)

Click on ´Create´, your new template is added to the Blueprint Templates list. Click on `Activate` next 
to your template's name so that the template is available to create Blueprints.

Go to `Blueprints` tab where you can find your new template. Click on `Create Blueprint` next to it.

Settings:

* Select Group: System.default (or another group for which this blueprint will be available).
* name: CentOS-7 virtual machine
* description: Launches a virtual machine with basic CentOS-7 OS

Find your new blueprint from the Blueprints list and click on `Activate`.

Finally go to 'Dashboard' and launch an instance. Once the instance is running, click 'Open in Browser'

In the example case, the cPouta image is configured to allow only SSH access using a rsa key for user cloud-user. 
Note also, that the firewall rules set in the blueprint template (default only SSH port 22 is open).

TODO: review firewalls settings

With the default firewalls settings (see blueprint template above), the virtual machine can only be accessed 
via SSH and using the Pebbles private key (user downloads it from `Account` tab, before launching the machine).
The UI gives the instructions to connect to the virtual machine, similar to: ssh cloud-user@xxx.xxx.xxx.xxx.


Creating your own cPouta images for Pebbles
===========================================

You can create blueprint templates and bluprints in Pebbles from your own custom images. The instructions below
describe what basic configuration your virtual machine should have and how the cPouta image should be created.

Virtual machine settings
------------------------
For compatibility with the standard Pebbles installation your custom virtual machine should comply with the following:

* The custom virtual machine was created in cPouta using the option Instance Boot Source:Boot from image
* TODO: test if VM launched with Instance Boot Source:Boot from snapshot also works
* TODO: confirm in explicit tests using in Pebbles an image that was created from a VM that had been launched with options:  Instance Boot Source:Boot from volume, Boot from image (creates a new volume) OR  Instance Boot Source:Boot from volume snapshot (creates a new volume)
* a cloud-user account exists in the virtual 
* TODO: ssh-server installation, cloud-user account settings, supported OS's...
* TODO: other connection possibilities, for ex VNC

cPouta image creation
---------------------

Once you have your custom virtual machine set up following the instructions above you need to create an image from it. That
image will the used by Pebbles to launch virtual machines using the OpenStackDriver.

In cPouta:
* Create an image from the virtual machine (make sure the image was created as mentioned above, otherwise it is possible
that Pebbles will fail to launch virtual machines)
* Note that images are created with RAW format, which takes as much disk space as the VM disk, for ex 80Gb. 
* For efficiency, you may consider transforming the image to QCOW2 (you may do so by using openstack python CLI
and qemu tools, this is not covered here though)

Adding your custom image to Pebbles
-----------------------------------
Follow the instruction at the beginning of this document.

TODO: what other settings may be needed compared to using an existing basic image.
