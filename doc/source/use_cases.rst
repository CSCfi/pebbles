.. _use-cases:

Use Cases
---------

The current major use cases revolve around setting up simple environments for
teaching and/or ad-hoc data analysis. 

Notebooks in containers
+++++++++++++++++++++++

See pb_ for a live example. 

1) User navigates to page
2) User logs in with SSO they already know
3) User selects appropriate blueprint and clicks a button
4) System provisions a Docker container from an image
5) System starts Jupyter/RStudio/similar inside container and forwards a port
6) User can access the HTML UI from his own browser

Virtual machines in the cloud.
++++++++++++++++++++++++++++++

1) User navigates to page
2) User logs in with SSO they already know
3) User selects appropriate blueprint and clicks a button
4) System provisions a virtual machine from cPouta_ using a provided base image
5) User can remote desktop into the IP address of the remote instance

.. _cPouta: https://research.csc.fi/cpouta
.. _PB: https://pb.csc.fi/


