from pouta_blueprints.models import Blueprint, Instance
from sqlalchemy.orm import load_only
import itertools


def apply_rules_blueprints(user, args={}):

    q = Blueprint.query
    if not user.is_admin:
        groups = user.groups
        group_ids = [group_item.id for group_item in groups]
        banned_groups = user.banned_groups
        banned_group_ids = [banned_group_item.id for banned_group_item in banned_groups]
        allowed_group_ids = set(group_ids) - set(banned_group_ids)  # do not allow the banned users
        q = q.filter(Blueprint.group_id.in_(allowed_group_ids))
        q = q.filter_by(is_enabled=True)
    if args.get('blueprint_id'):
        q = q.filter_by(id=args.get('blueprint_id'))

    return q


def get_group_blueprint_ids_for_instances(groups):

    # loading only id column rest will be deferred
    group_blueprints = [group_item.blueprints.options(load_only("id")).all() for group_item in groups]
    group_blueprints_flat = list(itertools.chain.from_iterable(group_blueprints))  # merge the list of lists into one list
    group_blueprints_id = [blueprint_item.id for blueprint_item in group_blueprints_flat]  # Get the ids in a list
    return group_blueprints_id


def apply_rules_instances(user, args={}):

    q = Instance.query
    if user.is_group_owner:  # Show only the instances of the blueprints which the group admin owns
        groups = user.groups
        group_blueprints_id = get_group_blueprint_ids_for_instances(groups)
        q = q.filter(Instance.blueprint_id.in_(group_blueprints_id))
    if args.get('instance_id'):
        q = q.filter_by(id=args.get('instance_id'))
    if not user.is_admin or not user.is_group_owner or args.get('show_only_mine'):
        q = q.filter_by(user_id=user.id)
    if not args.get('show_deleted'):
        q = q.filter(Instance.state != Instance.STATE_DELETED)
    if args.get('offset'):
        q = q.offset(args.get('offset'))
    if args.get('limit'):
        q = q.limit(args.get('limit'))

    return q
