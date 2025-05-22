import datetime
import random
import string

import kubernetes
import openshift.dynamic

"""
BuildClient provides a simplified interface for building custom images on OpenShift/OKD.
"""


class BuildClient():
    def __init__(self, build_namespace, registry, repo, k8s_api_client=None):
        self.build_namespace = build_namespace
        self.registry = registry
        self.repo = repo
        # either use given client or load service account based config
        if k8s_api_client:
            self.kubernetes_api_client = k8s_api_client
        else:
            kubernetes.config.load_incluster_config()
            self.kubernetes_api_client = kubernetes.client.ApiClient()
        self.osdc = openshift.dynamic.DynamicClient(self.kubernetes_api_client)

    def get_build(self, id, suppress_404=False):
        build_api = self.osdc.resources.get(api_version='build.openshift.io/v1', kind='Build')
        try:
            builds = build_api.get(namespace=self.build_namespace, label_selector=f'buildconfig={id}')
            if builds and builds.items:
                return builds.items[0]
            return None
        except kubernetes.client.ApiException as e:
            if e.status == 404 and suppress_404:
                return None
            raise e

    def get_buildconfig(self, name, suppress_404=False):
        bc_api = self.osdc.resources.get(api_version='build.openshift.io/v1', kind='BuildConfig')
        try:
            return bc_api.get(namespace=self.build_namespace, name=name)
        except kubernetes.client.ApiException as e:
            if e.status == 404 and suppress_404:
                return None
            raise e

    def get_imagestream(self, name, suppress_404=False):
        is_api = self.osdc.resources.get(api_version='image.openshift.io/v1', kind='ImageStream')
        try:
            return is_api.get(namespace=self.build_namespace, name=name)
        except kubernetes.client.ApiException as e:
            if e.status == 404 and suppress_404:
                return None
            raise e

    def delete_build(self, build_id, suppress_404=False):
        bc_api = self.osdc.resources.get(api_version='build.openshift.io/v1', kind='BuildConfig')
        try:
            return bc_api.delete(namespace=self.build_namespace, name=build_id)
        except kubernetes.client.ApiException as e:
            if e.status == 404 and suppress_404:
                return None
            raise e

    def delete_tag(self, name, tag, suppress_404=False):
        tag_api = self.osdc.resources.get(api_version='image.openshift.io/v1', kind='ImageStreamTag')
        try:
            return tag_api.delete(namespace=self.build_namespace, name=f'{name}:{tag}')
        except kubernetes.client.ApiException as e:
            if e.status == 404 and suppress_404:
                return None
            raise e

    def post_build(self, name, dockerfile):
        bc_api = self.osdc.resources.get(api_version='build.openshift.io/v1', kind='BuildConfig')
        is_api = self.osdc.resources.get(api_version='image.openshift.io/v1', kind='ImageStream')

        # create imagestream if necessary
        try:
            is_api.get(namespace=self.build_namespace, name=f'{name}')
        except kubernetes.client.ApiException as e:
            if e.status != 404:
                raise e
            is_spec = dict(
                apiVersion='image.openshift.io/v1',
                kind='ImageStream',
                metadata=dict(
                    name=f'{name}'
                ),
                spec=dict()
            )
            is_api.create(namespace=self.build_namespace, body=is_spec)

        # create disposable buildconfig
        # disposable build id
        build_id = f'{name}-{''.join(random.choice(string.ascii_lowercase) for _ in range(12))}'
        tag = datetime.datetime.now(datetime.UTC).strftime('%Y%m%d%H%M%S')
        bc_spec = dict(
            apiVersion='build.openshift.io/v1',
            kind='BuildConfig',
            metadata=dict(
                name=build_id,
                labels=dict(
                    source='build-proxy',
                )
            ),
            spec=dict(
                output=dict(
                    to=dict(
                        kind='ImageStreamTag',
                        name=name + ':' + tag,
                    )
                ),
                source=dict(dockerfile=dockerfile, ),
                strategy=dict(type='docker', dockerStrategy=dict(), ),
                resources=dict(limits=dict(cpu='1'), requests=dict(cpu='1'))
            ),
        )
        bc_api.create(namespace=self.build_namespace, body=bc_spec)

        # trigger build
        br_spec = dict(
            apiVersion='build.openshift.io/v1',
            kind='BuildRequest',
            metadata=dict(
                name=build_id,
            ),
            triggeredBy=[
                dict(message='Triggered by build-proxy'),
            ],
        )
        self.osdc.request(
            path=f'/apis/build.openshift.io/v1/namespaces/{self.build_namespace}/buildconfigs/{name}/instantiate',
            method='POST',
            body=br_spec,
        )

        return dict(
            build_id=build_id,
            registry=self.registry,
            repo=self.repo,
            name=name,
            tag=tag,
        )
