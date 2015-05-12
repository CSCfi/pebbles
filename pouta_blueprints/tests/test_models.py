import datetime

from pouta_blueprints.tests.base import db, BaseTestCase
from pouta_blueprints.models import User, Blueprint, Plugin, Instance


class ModelsTestCase(BaseTestCase):
    def setUp(self):
        db.create_all()
        u = User("user@example.org", "user", is_admin=False)
        self.known_user = u

        db.session.add(u)

        p1 = Plugin()
        p1.name = "TestPlugin"
        self.known_plugin_id = p1.id
        db.session.add(p1)

        b1 = Blueprint()
        b1.name = "TestBlueprint"
        b1.plugin = p1.id
        b1.cost_multiplier = 1.5
        self.known_blueprint = b1
        db.session.add(b1)

        db.session.commit()

    def test_calculate_instance_cost(self):
        i1 = Instance(self.known_blueprint, self.known_user)
        i1.provisioned_at = datetime.datetime(2015, 1, 1, 12, 0)
        i1.deprovisioned_at = datetime.datetime(2015, 1, 1, 12, 5)
        expected_cost = (1.5 * 5 * 60 / 3600)
        assert (expected_cost - 0.01) < i1.credits_spent() < (expected_cost + 0.01)
