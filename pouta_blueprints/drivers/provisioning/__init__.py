"""
Provisioning drivers
=====================

Provisioning drivers are what makes PB tick. There are several for different
backends. Currently it's possible to:

* provision OpenStack virtual machines (OpenStackDriver)
* provision Docker containers from a host pool that consists of OpenStack
  virtual machines (DockerDriver)

There is work ongoing about adding support for provisioning
containers from an OpenShift.

Each driver uses different settings that can be set by the admin. The ones for
DockerDriver are prepended DD_* . Both instances require M2M_CREDENTIAL_STORE
to access OpenStack API.

Drivers are implemented as plugins that are loaded dynamically by
:py:mod:`stevedore`
"""
