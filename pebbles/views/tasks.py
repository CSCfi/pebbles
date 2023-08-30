import logging
import time

import flask_restful as restful
from flask import Blueprint as FlaskBlueprint
from flask import abort, request
from flask_restful import marshal_with, fields, reqparse

from pebbles.models import Task
from pebbles.models import db
from pebbles.utils import requires_admin
from pebbles.views.commons import auth

tasks = FlaskBlueprint('tasks', __name__)

task_fields = {
    'id': fields.String,
    'kind': fields.String,
    'state': fields.String,
    'data': fields.Raw,
    'create_ts': fields.Integer,
    'complete_ts': fields.Integer,
    'update_ts': fields.Integer,
    'results': fields.Raw,
}


class TaskList(restful.Resource):
    get_parser = reqparse.RequestParser()
    get_parser.add_argument('kind', type=str, location='args')
    get_parser.add_argument('state', type=str, location='args')
    get_parser.add_argument('unfinished', type=bool, location='args')

    @auth.login_required
    @requires_admin
    @marshal_with(task_fields)
    def get(self):
        q = Task.query
        args = self.get_parser.parse_args()

        unfinished = args.get('unfinished', False)
        if unfinished:
            q = q.filter(Task.state.in_([Task.STATE_NEW, Task.STATE_PROCESSING]))

        kind = args.get('kind', None)
        if kind:
            q = q.filter_by(kind=kind)

        state = args.get('state', None)
        if state:
            q = q.filter_by(state=state)

        q = q.order_by(Task._create_ts)
        results = q.all()
        return results

    @auth.login_required
    @requires_admin
    @marshal_with(task_fields)
    def post(self):
        kind = request.json.get('kind')
        data = request.json.get('data')
        if not (kind and data):
            logging.warning('kind and data have to be defined')
            abort(422)

        try:
            task = Task(kind, Task.STATE_NEW, data)
            db.session.add(task)
            db.session.commit()
            return task
        except ValueError as ve:
            logging.warning('error posting task: %s', ve)
            return '%s' % ve, 422


class TaskView(restful.Resource):
    @auth.login_required
    @requires_admin
    @marshal_with(task_fields)
    def get(self, task_id):
        q = Task.query.filter_by(id=task_id)
        task = q.first()
        if not task:
            abort(404)
        return task

    @auth.login_required
    @requires_admin
    @marshal_with(task_fields)
    def patch(self, task_id):
        q = Task.query.filter_by(id=task_id)
        task = q.first()
        if not task:
            abort(404)
        try:
            task.state = request.json.get('state')
            task.update_ts = time.time()
            if task.state == Task.STATE_FINISHED:
                task.complete_ts = time.time()
            db.session.commit()
            return task
        except ValueError as ve:
            logging.warning('error patching task: %s', ve)
            return '%s' % ve, 422


class TaskAddResults(restful.Resource):
    # Admin can add more lines to task results
    parser = reqparse.RequestParser()
    parser.add_argument('results', type=str, required=True)

    @auth.login_required
    @requires_admin
    def put(self, task_id):
        args = self.parser.parse_args()
        task = Task.query.filter_by(id=task_id).first()
        if not task:
            logging.warning('Task %s does not exist', task_id)
            return dict(error='Task does not exist'), 404

        new_results = []

        if type(task.results) is list:
            new_results = task.results

        new_results.extend(args.results.splitlines())

        task.results = new_results

        try:
            db.session.commit()
            return task.results
        except ValueError as ve:
            logging.warning('error posting task: %s', ve)
            return '%s' % ve, 422
