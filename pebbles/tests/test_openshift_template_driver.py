import logging

import responses

from pebbles.tests.test_openshift_driver import OpenShiftDriverAccessMock
import pebbles.drivers.provisioning.openshift_template_driver as openshift_template_driver
from pebbles.tests.base import BaseTestCase

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class OpenShiftTemplateDriverTestCase(BaseTestCase):
    def setUp(self):
        pass

    @staticmethod
    def create_openshift_template_driver():
        config = dict(
            INSTANCE_DATA_DIR='/tmp',
            M2M_CREDENTIAL_STORE='',
            INTERNAL_API_BASE_URL='http://bogus/api/v1',
            TEST_MODE=True,
            PUBLIC_IPV4='10.0.0.1',
            EXTERNAL_HTTPS_PORT=443,
        )
        ostd = openshift_template_driver.OpenShiftTemplateDriver(logger, config)
        ostd._ap = OpenShiftDriverAccessMock(
            m2m_creds={
                'OSD_TEST_BASE_URL': 'https://localhost:8443/',
                'OSD_TEST_SUBDOMAIN': 'oso.example.com',
                'OSD_TEST_USER': 'm2m',
                'OSD_TEST_PASSWORD': 'machinehead',
            }
        )
        return ostd

    @responses.activate
    def test_provision_deprovision(self):
        ostd = self.create_openshift_template_driver()
        ostdam = ostd._get_access_proxy()
        osc = ostdam.get_openshift_client('TEST')

        user1_ns = 'user1-at-example-com-1111'

        # spawn a simple instance and destroy it
        ostdam.pbc_mock.add_instance_data('1001-ost', blueprint_id='bp-ostemplate-01')
        self.populate_responses(osc, user1_ns, 'pb-1001-ost')
        ostd.do_provision(token='foo', instance_id='1001-ost')
        ostd.do_deprovision(token='foo', instance_id='1001-ost')

    @staticmethod
    def populate_responses(osc, user1_ns, instance_name):
        oapi_ns = osc.oapi_base_url + '/namespaces/' + user1_ns
        kubeapi_ns = osc.kube_base_url + '/namespaces/' + user1_ns
        templateapi_ns = osc.template_base_url + '/namespaces/' + user1_ns

        # add a sample (minimal!) template
        responses.add(
            responses.GET,
            'http://example.org/template.yaml',
            body="""
              apiVersion: template.openshift.io/v1
              kind: Template
              objects:
                - apiVersion: v1
                  kind: DeploymentConfig
                  metadata:
                    name: testdc
                - apiVersion: v1
                  kind: Service
                - apiVersion: v1
                  kind: Route
            """
        )

        responses.add(
            responses.POST,
            templateapi_ns + '/processedtemplates',
            json={'objects': [
                {'apiVersion': 'v1', 'kind': 'DeploymentConfig', 'metadata': {'name': 'testdc'}},
                {'apiVersion': 'v1', 'kind': 'Service'},
                {'apiVersion': 'route.openshift.io/v1', 'kind': 'Route'},
            ]}
        )
        # first add provisioning responses
        responses.add(
            responses.GET,
            osc.oapi_base_url + '/projects/' + user1_ns,
        )

        responses.add(
            responses.POST,
            oapi_ns + '/deploymentconfigs',
        )

        responses.add(
            responses.GET,
            kubeapi_ns + '/pods',
            json=dict(
                items=[dict(
                    status=dict(
                        containerStatuses=[dict(name=instance_name, ready=True)],
                        phase='Running'))]
            )
        )
        responses.add(
            responses.POST,
            kubeapi_ns + '/services',
        )
        responses.add(
            responses.POST,
            oapi_ns + '/routes',
            json={'spec': {'host': '%s.%s' % (instance_name, osc.subdomain)}}
        )

        # then add deprovisioning responses
        responses.add(
            responses.GET,
            kubeapi_ns + '/replicationcontrollers',
            json={'items': [{'spec': {'replicas': 1}, 'metadata': {'name': '%s-1' % instance_name}}]}
        )
        responses.add(
            responses.PUT,
            kubeapi_ns + '/replicationcontrollers/%s-1' % instance_name,
        )
        responses.add(
            responses.GET,
            kubeapi_ns + '/replicationcontrollers/%s-1' % instance_name,
            json={'status': {'replicas': 0}, 'metadata': {'name': '%s-1' % instance_name}}
        )

        responses.add(
            responses.GET,
            kubeapi_ns + '/services',
            json={'items': [{'metadata': {'name': 'svc1'}}, {'metadata': {'name': 'svc2'}}]}
        )

        responses.add(
            responses.DELETE,
            oapi_ns + '/deploymentconfigs',
        )
        responses.add(
            responses.DELETE,
            kubeapi_ns + '/replicationcontrollers/%s-1' % instance_name,
        )
        responses.add(
            responses.DELETE,
            kubeapi_ns + '/configmaps',
        )
        responses.add(
            responses.DELETE,
            kubeapi_ns + '/secrets',
        )

        responses.add(
            responses.DELETE,
            oapi_ns + '/routes',
        )
        for svc_name in ('svc1', 'svc2'):
            responses.add(
                responses.DELETE,
                kubeapi_ns + '/services/%s' % svc_name,
            )
