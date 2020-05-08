"""
================
Pebbles overview
================

Pebbles is about provisioning cloud resources with a simple end-user
experience. Currently supported provisioning back-end is OpenStack. It's
possible to provision either full Virtual Machines or merely Docker containers
from a pool of hosts that Pebbles maintains.

Virtual machines can and typically do have their own IP address and for
containers a port can be forwarded for communication with software running on
the container.  Jupyter Notebooks or RStudio Server are good candidates for
inside a container.

.. NOTE:: Currently no authentication is done when accessing a container via a
    forwarded URL.  Anyone who knows the URL for a notebook can access it, the
    connection is not authenticated.  This is something to keep in mind as it has
    security implications. Scanning for all possible URLs may be difficult but in
    the current implementation confidentiality of data in notebooks is not
    guaranteed.  The upside is that many parties can access the same container
    if the URL is shared.


The resources are abstracted on two levels as Bluperint Templates and Environments:
  * **Environment templates** are created by system administrators who maintain the
    system.
  * **Environments** can be created based on an existing Environment templates by
    users with elevated but non-administrator rights. Regular users can then
    provision and access resources based on these environments.

The purpose of this divide is to let system administrators create types of
resource packages with limited freedom to modify the parameters delegated to
lower level elevated priviledge users.

.. NOTE:: All disk storage in Pebbles is more or less ephemeral. You are
   responsible for your data persistence!

User Types in Pebbles
---------------------

There are broadly four roles in a Pebbles instance:

1. Admin - Which is supposed to be the superuser of the system. Ability to
    invite new users, appoint workspace owners, create environment templates,
    environments, system and normal groups. System level priviledges : Access to
    the backend database, restart or delete running services.
2. Workspace Owner - Ability to create groups, appoint workspace managers , create
    environments and manage instances running in a workspace
3. Workspace Manager - Ability to create environments and manage instances
    running in a workspace
4. User - Able to launch instances if belonging to a workspace with
    environments.

A **workspace owner** is typically associated with costs tracking, e.g. a
professor or researcher. The workspace owner can create groups and promote other
users to be **workspace managers** to run basic day-to-day tasks.

Use Cases
---------

The current main use cases revolve around setting up simple environments for
teaching and/or ad-hoc data analysis.

Notebooks in containers
+++++++++++++++++++++++

See pb_ for a live example.

1) User navigates to page
2) User logs in with SSO they already know
3) User selects appropriate environment and clicks a button
4) System provisions a Docker container from an image
5) System starts Jupyter/RStudio/similar inside container and forwards a port
6) User can access the HTML UI from his own browser

Virtual machines in the cloud.
++++++++++++++++++++++++++++++

1) User navigates to page
2) User logs in with SSO they already know
3) User selects appropriate environment and clicks a button
4) System provisions a virtual machine from cPouta_ using a provided base image
5) User can remote desktop into the IP address of the remote instance

.. _cPouta: https://research.csc.fi/cpouta
.. _PB: https://pb.csc.fi/



"""
