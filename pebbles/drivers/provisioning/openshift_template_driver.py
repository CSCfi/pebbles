from pebbles.drivers.provisioning.openshift_driver import OpenShiftDriver
import requests
import yaml
import json


class OpenShiftTemplateDriver(OpenShiftDriver):
    """ OpenShift Template Driver allows provisioning instances in an existing OpenShift cluster,
        using an Openshift Template. It creates a project per user, identified by user email.
        It will create a PVC if defined in the template, and will retain it upon deprovisioning.
        All the templates require a label defined in the template, like - "label: app: <app_label>"

        Similar to the openshift driver, it needs credentials for the cluster.
        The credentials are placed in the same m2m creds file that OpenStack and Docker driver use.

        Since this driver is subclassed from OpenshiftDriver, it uses a lot of methods from it.
        """

    def get_configuration(self):
        """ Return the default config values which are needed for the
            plugin creation (via schemaform)
        """
        from pebbles.drivers.provisioning.openshift_template_driver_config import CONFIG

        config = CONFIG.copy()
        return config

    def _spawn_project_and_objects(self, oc, project_name, blueprint_config, instance=None, environment_vars=None):
        """ Create openshift objects from given template
        """
        self._create_project(oc, project_name)

        template_url = blueprint_config['os_template']
        if not template_url:
            raise RuntimeError('No template url given')

        try:
            template_url_data = requests.get(template_url)
            template_yaml = yaml.safe_load(template_url_data.text)
        except Exception as e:
            raise RuntimeError(e)

        if not template_yaml:
            raise RuntimeError("No template yaml could be loaded")

        if 'parameters' in template_yaml:
            template_params = template_yaml['parameters']
            for template_param in template_params:
                if(template_param['name'] in environment_vars):  # check if the user has passed env vars from the blueprint
                    env_template_param_val = environment_vars[template_param['name']]
                    if(env_template_param_val == "instance_name"):
                        template_param['value'] = instance['name']
                    else:
                        template_param['value'] = env_template_param_val

        template_json = json.dumps(template_yaml)  # rest api requires json str
        template_objects_resp = oc.make_request(api_type='template_oapi', namespace=project_name, object_kind='processedtemplates', data=template_json)
        template_objects_json = template_objects_resp.json()
        template_objects = template_objects_json['objects']

        dc_names = []  # names of deploymentconfigs
        route_data_resp = None
        for template_object in template_objects:
            object_kind = "%ss" % str.lower(str(template_object['kind']))
            object_data = template_object
            if (object_data['apiVersion'] != 'v1'):  # this is a hack for openshift specific objects eg. routes or dc
                object_data['apiVersion'] = 'v1'  # the processedtemplates endpoint gives the full apiVersion instead of just v1
            if(object_kind in ['services', 'persistentvolumeclaims', 'configmaps', 'secrets']):  # all k8 specific objects will need kubeapi
                api_type = 'kubeapi'
            else:
                api_type = 'oapi'

            if(object_kind == 'deploymentconfigs'):
                dc_names.append(template_object['metadata']['name'])

            object_data_resp = None
            try:
                object_data_resp = oc.make_request(api_type=api_type, namespace=project_name, object_kind=object_kind, data=object_data)
            except RuntimeError as e:
                e_reason = json.loads(e.message)['reason']
                if(e_reason == "AlreadyExists"):  # If persistent storage (or in error cases, anything else) exists, then do not create it
                    self.logger.info("%s %s already exists" % (object_kind, object_data['metadata']['name']))
                else:
                    raise RuntimeError(e)

            if(object_kind == 'routes'):
                route_data_resp = object_data_resp

        if not route_data_resp:
            raise RuntimeError("No route(s) found in the template")

        route_data_resp_json = route_data_resp.json()

        for dc_name in dc_names:  # the pods have label for deploymentconfig instead of a global one
            pod_selector_params = dict(labelSelector='deploymentconfig=%s' % dc_name)
            self._wait_for_pod_creation(oc, project_name, pod_selector_params, None)

        return dict(route='https://%s/' % route_data_resp_json['spec']['host'])

    def _delete_objects(self, oc, project, instance, blueprint_config):
        """ Delete openshift objects based on the given template
        """
        name = instance['name']
        instance_id = instance['id']

        app_label = blueprint_config['app_label']  # app_label is required for all blueprints for searching and deleting
        params = dict(labelSelector='app=%s' % app_label)
        res = oc.make_delete_request(
            namespace=project,
            object_kind='deploymentconfigs',
            raise_on_failure=False,
            params=params
        )
        if not res.ok:
            if res.status_code == 404:
                self.logger.warning('do_deprovision: DC not found, assuming deleted: %s' % name)
            else:
                raise RuntimeError(res.reason)

        # find rc
        rc_list = oc.search_by_label(
            api_type='kubeapi',
            namespace=project,
            object_kind='replicationcontrollers',
            params=params
        )
        # then set replicas to 0 and let pods die
        for rc in rc_list:
            self._scale_rc(oc, project, rc, 0)

        # remove rc
        for rc in rc_list:
            res = oc.make_delete_request(
                api_type='kubeapi',
                namespace=project,
                object_kind='replicationcontrollers',
                object_id=rc['metadata']['name'],
                raise_on_failure=False,
            )
            if not res.ok:
                if res.status_code == 404:
                    self.logger.warning('do_deprovision: RC not found, assuming deleted: %s' % name)
                else:
                    raise RuntimeError(res.reason)

        # remove configmaps
        res = oc.make_delete_request(
            api_type='kubeapi',
            namespace=project,
            object_kind='configmaps',
            raise_on_failure=False,
            params=params
        )
        if not res.ok:
            if res.status_code == 404:
                self.logger.warning('do_deprovision: ConfigMap not found, assuming deleted: %s' % name)
            else:
                raise RuntimeError(res.reason)

        # remove secrets
        res = oc.make_delete_request(
            api_type='kubeapi',
            namespace=project,
            object_kind='secrets',
            raise_on_failure=False,
            params=params
        )
        if not res.ok:
            if res.status_code == 404:
                self.logger.warning('do_deprovision: Secret not found, assuming deleted: %s' % name)
            else:
                raise RuntimeError(res.reason)

        # remove routes
        res = oc.make_delete_request(
            namespace=project,
            object_kind='routes',
            raise_on_failure=False,
            params=params
        )
        if not res.ok:
            if res.status_code == 404:
                self.logger.warning('do_deprovision: route not found, assuming deleted: %s' % name)
            else:
                raise RuntimeError(res.reason)

        # find svc
        svc_list = oc.search_by_label(
            api_type='kubeapi',
            namespace=project,
            object_kind='services',
            params=params
        )
        # remove services
        for svc in svc_list:
            res = oc.make_delete_request(
                api_type='kubeapi',
                namespace=project,
                object_kind='services',
                object_id=svc['metadata']['name'],
                raise_on_failure=False,
            )
            if not res.ok:
                if res.status_code == 404:
                    self.logger.warning('do_deprovision: RC not found, assuming deleted: %s' % name)
                else:
                    raise RuntimeError(res.reason)

        self.logger.debug('do_deprovision done for %s' % instance_id)
