import datetime
import logging
import random
import string
import base64
import json

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

    def create_sa_pull_creds(self, sa_name, duration_seconds=600) -> tuple[str, int]:
        """
        Construct dockercfg pull credentials for a given service account in build namespace.
        Returns a tuple of dockercfg data and expiry timestamp for caching.
        """
        logging.debug('BuildClient creating sa_pull_creds')

        # Mimics: oc create token <sa> --duration=60s
        tr_api = self.osdc.resources.get(api_version='v1', kind='ServiceAccount')
        body = {
            'apiVersion': 'authentication.k8s.io/v1',
            'kind': 'TokenRequest',
            'spec': {
                'audiences': ['https://kubernetes.default.svc'],
                'expirationSeconds': duration_seconds
            }
        }
        try:
            resp = tr_api.subresources['token'].create(
                name=sa_name,
                namespace=self.build_namespace,
                body=body
            )
            token = resp['status']['token']
        except kubernetes.client.ApiException as e:
            raise RuntimeWarning(e)
        # Decode "exp" from JWT payload
        payload_b64 = token.split('.')[1]
        payload_b64 += '=' * (-len(payload_b64) % 4)  # fix padding
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        token_expiry_ts = payload.get('exp', 0)
        # Build .dockercfg JSON for the registry
        auth_str = f'serviceaccount:{token}'  # username:password
        auth_b64 = base64.b64encode(auth_str.encode('utf-8')).decode('utf-8')
        dockercfg = {
            self.registry: {
                "auth": auth_b64
            }
        }
        dockercfg_json = json.dumps(dockercfg, separators=(',', ':'))
        dockercfg_b64 = base64.b64encode(dockercfg_json.encode('utf-8')).decode('utf-8')

        return dockercfg_b64, token_expiry_ts

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

    def post_build(self, name, dockerfile, build_pod_memory='1Gi'):
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
                resources=dict(
                    limits=dict(cpu='1', memory=build_pod_memory),
                    requests=dict(cpu='1', memory=build_pod_memory)
                )
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
