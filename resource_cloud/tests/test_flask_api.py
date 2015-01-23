import unittest
import base64
import json

from resource_cloud.tests.base import db, BaseTestCase
from resource_cloud.models import User, Resource


class FlaskApiTestCase(BaseTestCase):
    def setUp(self):
        db.create_all()
        db.session.add(User("admin@admin.com", "admin", is_admin=True))
        r = Resource()
        r.name = "TestResource"
        db.session.add(r)
        db.session.commit()

    def test_first_user(self):
        db.drop_all()
        db.create_all()
        headers = [('Content-Type', 'application/json')]
        response = self.client.post('/api/v1/initialize',
                                    headers=headers,
                                    data=json.dumps({'email': 'admin@admin.com',
                                                     'password': 'admin'}))
        self.assertEqual(response.status_code, 200)

    def test_anonymous_get_users(self):
        response = self.client.get('/api/v1/users',
                                   content_type="application/json")
        self.assertEqual(response.status_code, 401)

    def test_authenticated_get_users(self):
        headers = [('Content-Type', 'application/json')]
        response = self.client.post('/api/v1/sessions',
                                    headers=headers,
                                    data=json.dumps({'email': 'admin@admin.com',
                                                     'password': 'admin'}))
        token = response.json['token']
        headers = [('Accept', 'application/json')]
        token_b64 = base64.b64encode(bytes('%s:' % token, 'ascii')).decode('ascii')
        headers.append(('Authorization', 'Basic %s' % token_b64))
        headers.append(('token', token_b64))
        response = self.client.get('/api/v1/users',
                                   headers=headers,
                                   content_type="application/json")

        self.assertEqual(response.status_code, 200)

if __name__ == '__main__':
    unittest.main()
