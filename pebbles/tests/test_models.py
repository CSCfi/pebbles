import datetime
from pebbles.tests.base import db, BaseTestCase
from pebbles.models import User, Group, Blueprint, BlueprintTemplate, Plugin, Instance


class ModelsTestCase(BaseTestCase):
    def setUp(self):
        db.create_all()
        u = User("user@example.org", "user", is_admin=False)
        self.known_user = u

        db.session.add(u)

        g = Group('Group1')
        self.known_group = g
        db.session.add(g)

        p1 = Plugin()
        p1.name = "TestPlugin"
        self.known_plugin_id = p1.id
        db.session.add(p1)

        t1 = BlueprintTemplate()
        t1.name = 'EnabledTestTemplate'
        t1.plugin = p1.id
        t1.is_enabled = True
        t1.allowed_attrs = ['cost_multiplier']
        db.session.add(t1)
        self.known_template_id = t1.id

        b1 = Blueprint()
        b1.name = "TestBlueprint"
        b1.template_id = t1.id
        b1.group_id = g.id
        # b1.cost_multiplier = 1.5
        b1.config = {
            'cost_multiplier': '1.5'
        }
        self.known_blueprint = b1
        db.session.add(b1)

        db.session.commit()

    def test_email_unification(self):
        u1 = User("UsEr1@example.org", "user")
        u2 = User("User2@example.org", "user")
        db.session.add(u1)
        db.session.add(u2)
        x1 = User.query.filter_by(email="USER1@EXAMPLE.ORG").first()
        x2 = User.query.filter_by(email="user2@Example.org").first()
        assert u1 == x1
        assert u1.email == x1.email
        assert u2 == x2
        assert u2.email == x2.email

    def test_add_duplicate_user_will_fail(self):
        u1 = User("UsEr1@example.org", "user")
        db.session.add(u1)
        u2 = User("User1@example.org", "user")
        db.session.add(u2)
        with self.assertRaises(Exception):
            db.session.commit()

    def test_calculate_instance_cost(self):
        i1 = Instance(self.known_blueprint, self.known_user)
        i1.provisioned_at = datetime.datetime(2015, 1, 1, 12, 0)
        i1.deprovisioned_at = datetime.datetime(2015, 1, 1, 12, 5)
        expected_cost = (1.5 * 5 * 60 / 3600)
        assert (expected_cost - 0.01) < i1.credits_spent() < (expected_cost + 0.01)

    def test_instance_states(self):
        i1 = Instance(self.known_blueprint, self.known_user)
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
