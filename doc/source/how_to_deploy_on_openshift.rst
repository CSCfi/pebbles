How to launch a Pebbles service on Rahti
****************************************

Prerequisites
=============

* Account on Rahti/Rahti-int
* OpenShift command line tools
* See Rahti/Rahti-int documention to get the basic bootstrapping done
* Pebbles source tree

Deployment
==========

Create a new project for your deployment::

    $ oc new-project pebbles-$USER

In the source directory, create the server from the template::

    $ oc process SOURCE_REPOSITORY_REF=refactor/openshift -f deployment/pebbles-template.yml | oc apply -f -

