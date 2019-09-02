import json

import kubernetes
from kubernetes import client as kc
from kubernetes.client.rest import ApiException

from pebbles.drivers.provisioning import base_driver

APP_DOMAIN = '127-0-0-1.nip.io'


class KubernetesLocalDriver(base_driver.ProvisioningDriverBase):
    # noinspection PyCompatibility
    def __init__(self, logger, config):
        super().__init__(logger, config)
        kubernetes.config.load_incluster_config()

    def do_provision(self, token, instance_id):
        pbclient = self.get_pb_client(token)
        instance = pbclient.get_instance(instance_id)

        deployment = self.create_deployment_object(instance)
        kc.AppsV1Api().create_namespaced_deployment(
            namespace='default', body=deployment
        )

        service = self.create_service_object(instance)
        kc.CoreV1Api().create_namespaced_service(
            namespace='default', body=service
        )

        ingress = self.create_ingress_object(instance)
        kc.NetworkingV1beta1Api().create_namespaced_ingress(
            namespace='default', body=ingress
        )

        instance_data = {
            'endpoints': [dict(
                name='https',
                access='http://%s-%s' % (instance['name'], APP_DOMAIN)
            )]
        }

        pbclient.do_instance_patch(instance_id, {'instance_data': json.dumps(instance_data)})

    def do_deprovision(self, token, instance_id):
        pbclient = self.get_pb_client(token)
        instance = pbclient.get_instance(instance_id)

        # remove deployment
        try:
            kc.AppsV1Api().delete_namespaced_deployment(
                namespace='default',
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
                namespace='default',
                name=instance['name']
            )
        except ApiException as e:
            if e.status == 404:
                self.logger.warn('Service not found, assuming it is already deleted')
            else:
                raise e

        # remove ingress
        try:
            kc.NetworkingV1beta1Api().delete_namespaced_ingress(
                namespace='default',
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
    def create_deployment_object(instance):
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
                                image='jupyter/minimal-notebook',
                                args=["jupyter", "notebook", "--NotebookApp.token=''"]
                            )
                        ]
                    )
                )
            )
        )
        return deployment

    @staticmethod
    def create_service_object(instance):
        service = kc.V1Service(
            metadata=kc.V1ObjectMeta(
                name=instance['name'],
            ),
            spec=kc.V1ServiceSpec(
                selector=dict(name=instance['name']),
                ports=[kc.V1ServicePort(
                    port=8888,
                    target_port=8888
                )]
            )
        )
        return service

    @staticmethod
    def create_ingress_object(instance):
        ingress = kc.ExtensionsV1beta1Ingress(
            metadata=kc.V1ObjectMeta(
                name=instance['name'],
            ),
            spec=kc.ExtensionsV1beta1IngressSpec(
                rules=[
                    kc.NetworkingV1beta1IngressRule(
                        host='%s-%s' % (instance['name'], APP_DOMAIN),
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
