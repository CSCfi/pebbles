from pebbles.tests.base import db, BaseTestCase
from pebbles.models import User, Workspace, Environment, EnvironmentTemplate, Instance


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
        t1.cluster = 'dummy_cluster_1'
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
