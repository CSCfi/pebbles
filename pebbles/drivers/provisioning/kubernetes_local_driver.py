import json
import os

import kubernetes
from kubernetes import client as kc
from kubernetes.client.rest import ApiException

from pebbles.drivers.provisioning import base_driver


class KubernetesLocalDriver(base_driver.ProvisioningDriverBase):
    # noinspection PyCompatibility
    def __init__(self, logger, config):
        super().__init__(logger, config)
        kubernetes.config.load_incluster_config()
        with open('/var/run/secrets/kubernetes.io/serviceaccount/namespace', mode='r') as f:
            self.namespace = f.read()

        self.app_domain = os.environ.get('INSTANCE_APP_DOMAIN')
        if not self.app_domain:
            self.app_domain = '127.0.0.1.nip.io'

    def do_provision(self, token, instance_id):
        pbclient = self.get_pb_client(token)
        instance = pbclient.get_instance(instance_id)
        blueprint = pbclient.get_instance_blueprint(instance_id)

        deployment = self.create_deployment_object(instance, blueprint)
        self.logger.debug('creating deployment %s' % deployment.to_str())
        kc.AppsV1Api().create_namespaced_deployment(
            namespace=self.namespace, body=deployment
        )

        service = self.create_service_object(instance, blueprint)
        self.logger.debug('creating service %s' % service.to_str())
        kc.CoreV1Api().create_namespaced_service(
            namespace=self.namespace, body=service
        )

        ingress = self.create_ingress_object(instance)
        self.logger.debug('creating ingress %s' % ingress.to_str())
        kc.ExtensionsV1beta1Api().create_namespaced_ingress(
            namespace=self.namespace, body=ingress
        )

        instance_data = {
            'endpoints': [dict(name='https', access='http://%s' % self.get_instance_hostname(instance))]
        }

        pbclient.do_instance_patch(instance_id, {'instance_data': json.dumps(instance_data)})

    def do_deprovision(self, token, instance_id):
        pbclient = self.get_pb_client(token)
        instance = pbclient.get_instance(instance_id)

        # remove deployment
        try:
            kc.AppsV1Api().delete_namespaced_deployment(
                namespace=self.namespace,
                name=instance['name']
            )
        except ApiException as e:
            if e.status == 404:
                self.logger.warn('Instance not found, assuming it is already deleted')
            else:
                raise e

        # remove service
        try:
            kc.CoreV1Api().delete_namespaced_service(
                namespace=self.namespace,
                name=instance['name']
            )
        except ApiException as e:
            if e.status == 404:
                self.logger.warn('Service not found, assuming it is already deleted')
            else:
                raise e

        # remove ingress
        try:
            kc.ExtensionsV1beta1Api().delete_namespaced_ingress(
                namespace=self.namespace,
                name=instance['name']
            )
        except ApiException as e:
            if e.status == 404:
                self.logger.warn('Ingress not found, assuming it is already deleted')
            else:
                raise e

    def do_update_connectivity(self, token, instance_id):
        pass

    def do_housekeep(self, token):
        pass

    def get_running_instance_logs(self, token, instance_id):
        pass

    @staticmethod
    def create_deployment_object(instance, blueprint):

        blueprint_config = blueprint['full_config']

        # create a dict out of space separated list of VAR=VAL entries
        env_var_array = blueprint_config.get('environment_vars', '').split()
        env_var_dict = {k: v for k, v in [x.split('=') for x in env_var_array]}
        env_var_dict['INSTANCE_ID'] = instance['id']
        env_var_list = [kc.V1EnvVar(x, env_var_dict[x]) for x in env_var_dict.keys()]

        deployment = kc.V1Deployment(
            metadata=kc.V1ObjectMeta(name=instance['name']),
            spec=kc.V1DeploymentSpec(
                selector={'matchLabels': {'name': instance['name']}},
                template=kc.V1PodTemplateSpec(
                    metadata=kc.V1ObjectMeta(labels={'name': instance['name']}),
                    spec=kc.V1PodSpec(
                        automount_service_account_token=False,
                        containers=[
                            kc.V1Container(
                                name='test',
                                image=blueprint_config['image'],
                                args=blueprint_config['args'].split(),
                                env=env_var_list,
                            )
                        ]
                    )
                )
            )
        )
        return deployment

    @staticmethod
    def create_service_object(instance, blueprint):

        blueprint_config = blueprint['full_config']

        service = kc.V1Service(
            metadata=kc.V1ObjectMeta(
                name=instance['name'],
            ),
            spec=kc.V1ServiceSpec(
                selector=dict(name=instance['name']),
                ports=[kc.V1ServicePort(
                    port=8888,
                    target_port=blueprint_config['port']
                )]
            )
        )
        return service

    def create_ingress_object(self, instance):
        ingress = kc.ExtensionsV1beta1Ingress(
            metadata=kc.V1ObjectMeta(
                name=instance['name'],
            ),
            spec=kc.ExtensionsV1beta1IngressSpec(
                rules=[
                    kc.NetworkingV1beta1IngressRule(
                        host=self.get_instance_hostname(instance),
                        http=kc.NetworkingV1beta1HTTPIngressRuleValue(
                            paths=[
                                kc.NetworkingV1beta1HTTPIngressPath(
                                    backend=kc.NetworkingV1beta1IngressBackend(
                                        service_port=8888,
                                        service_name=instance['name']
                                    )
                                )
                            ]
                        )
                    )
                ]
            )
        )
        return ingress

    def get_instance_hostname(self, instance):
        return '%s.%s' % (instance['name'], self.app_domain)
