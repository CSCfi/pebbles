"""
Provisioning drivers
=====================

Provisioning drivers are what makes PB tick. There are several for different
backends. Currently it's possible to:

* provision OpenStack virtual machines (OpenStackDriver)
* provision Docker containers from a host pool that consists of OpenStack
  virtual machines (DockerDriver)
* provision containers from OpenShift (OpenShiftDriver)

The ones for DockerDriver are prepended DD_* . All drivers require the
variable M2M_CREDENTIAL_STORE for credentials to OpenStack/OpenShift. The
variable should point to a JSON file that contains

For OpenStackDriver and DockerDriver

* OS_USERNAME
* OS_PASSWORD
* OS_TENANT_NAME
* OS_AUTH_URL

To a v2 endpoint (v3 support will come eventually).

For OpenShiftDriver:

* OSD_*_BASE_URL
* OSD_*_SUBDOMAIN
* OSD_*_USER
* OSD_*_PASSWORD

Where * is the name of the OpenShift installation (the system can handle
multiple openshifts).


Drivers are implemented as plugins that are loaded dynamically by
:py:mod:`stevedore` .
"""
