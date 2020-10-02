from pebbles.tests.base import db, BaseTestCase
from pebbles.models import User, Workspace, Environment, EnvironmentTemplate, Instance, NamespacedKeyValue


class ModelsTestCase(BaseTestCase):
    def setUp(self):
        db.create_all()
        u = User("user@example.org", "user", is_admin=False, email_id="user@example.org")
        self.known_user = u

        db.session.add(u)

        ws = Workspace('Workspace1')
        self.known_group = ws
        db.session.add(ws)

        t1 = EnvironmentTemplate()
        t1.name = 'EnabledTestTemplate'
        t1.cluster = 'OpenShiftLocalDriver'
        t1.is_enabled = True
        t1.allowed_attrs = ['cost_multiplier']
        db.session.add(t1)
        self.known_template_id = t1.id

        b1 = Environment()
        b1.name = "TestEnvironment"
        b1.template_id = t1.id
        b1.workspace_id = ws.id
        # b1.cost_multiplier = 1.5
        b1.config = {
            'cost_multiplier': '1.5'
        }
        self.known_environment = b1
        db.session.add(b1)

        db.session.commit()

    def test_eppn_unification(self):
        u1 = User("UsEr1@example.org", "user")
        u2 = User("User2@example.org", "user")
        db.session.add(u1)
        db.session.add(u2)
        x1 = User.query.filter_by(eppn="USER1@EXAMPLE.ORG").first()
        x2 = User.query.filter_by(eppn="user2@Example.org").first()
        assert u1 == x1
        assert u1.eppn == x1.eppn
        assert u2 == x2
        assert u2.eppn == x2.eppn

    def test_add_duplicate_user_will_fail(self):
        u1 = User("UsEr1@example.org", "user")
        db.session.add(u1)
        u2 = User("User1@example.org", "user")
        db.session.add(u2)
        with self.assertRaises(Exception):
            db.session.commit()

    def test_instance_states(self):
        i1 = Instance(self.known_environment, self.known_user)
        for state in Instance.VALID_STATES:
            i1.state = state

        invalid_states = [x + 'foo' for x in Instance.VALID_STATES]
        invalid_states.append('')
        invalid_states.extend([x.upper() for x in Instance.VALID_STATES])

        for state in invalid_states:
            try:
                i1.state = state
                self.fail('invalid state %s not detected' % state)
            except ValueError:
                pass

    def test_schema_validation(self):
        schema = {
            'type': 'object',
            'properties': {
                'BOOL_VAR': {'type': 'boolean'},
                'STR_VAR': {'type': 'string'},
                'STR_OPTIONAL_VAR': {'type': 'string'},
                'INT_VAR': {'type': 'integer'},
            },
            'required': [
                'BOOL_VAR',
                'INT_VAR',
                'STR_VAR'
            ]
        }
        value = {
            'BOOL_VAR': True,
            'STR_VAR': 'STR_VAL',
            'STR_OPTIONAL_VAR': 'TEST_VAL',
            'INT_VAR': 1,
        }
        # Normal data
        n1 = NamespacedKeyValue('TestDriver_1', 'cluster_config', schema)
        n1_value = value.copy()
        n1.value = n1_value

        # Optional field can have empty value
        n2 = NamespacedKeyValue('TestDriver_2', 'cluster_config', schema)
        n2_value = value.copy()
        n2_value['STR_OPTIONAL_VAR'] = ''
        n2.value = n2_value

        # Not providing all the fields mentioned in the schema
        n3 = NamespacedKeyValue('TestDriver_3', 'cluster_config', schema)
        n3_value = value.copy()
        del n3_value['BOOL_VAR']
        try:
            n3.value = n3_value
        except:
            self.assertRaises(KeyError)

        # Providing a new field which doesn't exist in the schema
        n4 = NamespacedKeyValue('TestDriver_4', 'cluster_config', schema)
        n4_value = value.copy()
        n4_value['NEW_VAR'] = 'NEW_VAL'
        try:
            n4.value = n4_value
        except:
            self.assertRaises(ValueError)

        # Incorrect value type for the variable
        n5 = NamespacedKeyValue('TestDriver_5', 'cluster_config', schema)
        n5_value = value.copy()
        n5_value['INT_VAR'] = 'Truth'
        try:
            n5.value = n5_value
        except:
            self.assertRaises(TypeError)

        # Field in schema changed but no corresponding value added
        n6 = NamespacedKeyValue('TestDriver_6', 'cluster_config', schema)
        n6_value = value.copy()
        n6_schema = schema.copy()
        n6_schema['properties']['INT_NEW_VAR'] = {'type': 'integer'}
        n6.schema = n6_schema
        try:
            n6.value = n6_value
        except:
            self.assertRaises(KeyError)
