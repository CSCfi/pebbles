from pebbles.models import Blueprint, BlueprintTemplate, Instance, User, GroupUserAssociation
from pebbles.views.commons import is_group_manager
from sqlalchemy import or_, and_
from sqlalchemy.orm import load_only
from sqlalchemy.sql.expression import true
import itertools
import datetime


def apply_rules_blueprint_templates(user, args=None):
    q = BlueprintTemplate.query
    if not user.is_admin:
        query_exp = BlueprintTemplate.is_enabled == true()
        q = q.filter(query_exp)
    if args is not None and 'template_id' in args:
        q = q.filter_by(id=args.get('template_id'))

    return q


def apply_rules_blueprints(user, args=None):
    q = Blueprint.query
    if not user.is_admin:
        group_user_objs = GroupUserAssociation.query.filter_by(user_id=user.id, manager=False).all()
        user_group_ids = [group_user_obj.group.id for group_user_obj in group_user_objs]
        banned_group_ids = [banned_group_item.id for banned_group_item in user.banned_groups.all()]
        allowed_group_ids = set(user_group_ids) - set(banned_group_ids)  # do not allow the banned users

        # Start building query expressions based on the condition that :
        # a group manager can see all of his blueprints and only enabled ones of other groups
        query_exp = Blueprint.is_enabled == true()
        allowed_group_ids_exp = None
        if allowed_group_ids:
            allowed_group_ids_exp = Blueprint.group_id.in_(allowed_group_ids)
        query_exp = and_(allowed_group_ids_exp, query_exp)

        manager_group_ids = get_manager_group_ids(user)
        manager_group_ids_exp = None
        if manager_group_ids:
            manager_group_ids_exp = Blueprint.group_id.in_(manager_group_ids)
        query_exp = or_(query_exp, manager_group_ids_exp)
        q = q.filter(query_exp)

    if args is not None and 'blueprint_id' in args:
        q = q.filter_by(id=args.get('blueprint_id'))

    return q


def apply_rules_export_blueprints(user):
    q = Blueprint.query
    if not user.is_admin:
        manager_group_ids = get_manager_group_ids(user)
        query_exp = None
        if manager_group_ids:
            query_exp = Blueprint.group_id.in_(manager_group_ids)
        q = q.filter(query_exp)
    return q


def apply_rules_export_statistics(stat_type, args=None):
    if stat_type == "institutions" or stat_type == "users":
        q = User.query
    elif stat_type == "quartals":
        q = User.query.add_columns(User.joining_date)
    if args:
        start = args.get("start")
        end = args.get("end")
        start_null = datetime.datetime.strptime('2000-01-01 00:00:00', '%Y-%m-%d %H:%M:%S')
        if start == start_null and (stat_type == "users" or stat_type == "institutions"):
            q = q.filter(User.is_active).filter(or_(User.joining_date.is_(None),
                                                    User.joining_date <= end))
        else:
            q = q.filter(User.is_active).filter(and_(User.joining_date <= end,
                                                     User.joining_date >= start))
    else:
        q = q.filter_by(is_active=True)
    return q


def apply_rules_export_monthly_instances(args=None):
    q = Instance.query

    if args:
        start = args.get('start')
        end = args.get('end')
        q = q.filter(and_(Instance.provisioned_at <= end,
                          Instance.provisioned_at >= start))
    return q


def apply_rules_instances(user, args=None):
    q = Instance.query
    if not user.is_admin:
        q1 = q.filter_by(user_id=user.id)
        if is_group_manager(user):  # show only the instances of the blueprints which the group manager holds
            group_blueprints_id = get_group_blueprint_ids_for_instances(user, manager=True)
            q2 = q.filter(Instance.blueprint_id.in_(group_blueprints_id))
            q = q1.union(q2)
        else:
            q = q1
    if args is None or not args.get('show_deleted'):
        q = q.filter(Instance.state != Instance.STATE_DELETED)
    if args is not None:
        if 'instance_id' in args:
            q = q.filter_by(id=args.get('instance_id'))
        if args.get('show_only_mine'):
            q = q.filter_by(user_id=user.id)
        if 'offset' in args:
            q = q.offset(args.get('offset'))
        if 'limit' in args:
            q = q.limit(args.get('limit'))
    return q


def apply_rules_users(args={}):
    q = User.query

    if 'filter_str' in args and args.filter_str:
        filter_str = str.lower(args.filter_str)
        q = q.filter(User._eppn.contains(filter_str))

    if 'user_type' in args and args.user_type:
        user_type = args.get('user_type')
        if user_type == 'Admins':
            q = q.filter_by(is_admin=True)
        elif user_type == 'Group Owners':
            q = q.filter_by(is_group_owner=True)
        elif user_type == 'Active':
            q = q.filter_by(is_active=True)
        elif user_type == 'Inactive':
            q = q.filter_by(is_active=False)
        elif user_type == 'Blocked':
            q = q.filter_by(is_blocked=True)

    if 'page' and 'page_size' in args:
        page = args.get('page')
        page_size = args.get('page_size')
        try:  # page and page_size can be None sometimes
            q = q.offset(page * page_size)
            q = q.limit(page_size)
        except:
            pass
    return q

###############################################
# all the helper functions for the rules go here
###############################################


def get_manager_group_ids(user):
    """Return the group ids for the user's managed groups"""
    # the result shall contain the owners of the groups too as they are managers by default
    group_manager_objs = GroupUserAssociation.query.filter_by(user_id=user.id, manager=True).all()
    manager_group_ids = [group_manager_obj.group.id for group_manager_obj in group_manager_objs]
    return manager_group_ids


def get_group_blueprint_ids_for_instances(user, manager=None):
    """Return the valid blueprint ids based on user's groups to be used in instances view"""
    group_user_query = GroupUserAssociation.query
    if manager:  # if we require only managed groups
        group_user_objs = group_user_query.filter_by(user_id=user.id, manager=True).all()
    else:  # get the normal user groups
        group_user_objs = group_user_query.filter_by(user_id=user.id).all()
    groups = [group_user_obj.group for group_user_obj in group_user_objs]
    # loading only id column rest will be deferred
    group_blueprints = [group_item.blueprints.options(load_only("id")).all() for group_item in groups]
    group_blueprints_flat = list(itertools.chain.from_iterable(group_blueprints))  # merge the list of lists into one list
    group_blueprints_id = [blueprint_item.id for blueprint_item in group_blueprints_flat]  # Get the ids in a list
    return group_blueprints_id
