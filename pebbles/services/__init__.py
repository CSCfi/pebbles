""" Services are software components used in multiple parts of the software.
The only current service OpenStackService began it's life as parts of the
OpenStackDriver. Then when DockerDriver required access to OpenStack APIs as
well the API access was split into it's own service that is used from two
locations.
"""
