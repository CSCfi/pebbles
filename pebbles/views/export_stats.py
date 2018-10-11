from flask.ext.restful import reqparse
from flask_restful.inputs import boolean
from flask import Blueprint as FlaskBlueprint
from datetime import datetime as dt
from operator import itemgetter

from pebbles.server import restful, app
from pebbles.views.commons import auth
from pebbles.utils import requires_admin
from pebbles.rules import apply_rules_export_statistics, apply_rules_export_monthly_instances

import ast

export_stats = FlaskBlueprint('export_stats', __name__)


class ExportStatistics(restful.Resource):
    parser = reqparse.RequestParser()
    parser.add_argument('start', type=str)
    parser.add_argument('end', type=str)
    parser.add_argument('filter', type=str)
    parser.add_argument('exclude', type=boolean)
    parser.add_argument('stat', type=str)

    def __init__(self):
        self.date_format = '%Y-%m-%d'
        self.month_count = 12
        # institution types
        if app.config['HAKA_INSTITUTION_LIST']:
            self.institution_list = ast.literal_eval(app.config['HAKA_INSTITUTION_LIST'])
        else:
            self.institution_list = {}
        # Quartal definition
        self.Q1 = [1, 2, 3]
        self.Q2 = [4, 5, 6]
        self.Q3 = [7, 8, 9]
        self.Q4 = [10, 11, 12]
        self.stat = None

    @auth.login_required
    @requires_admin
    def get(self):
        args = self.parser.parse_args()
        dates = self.check_date_input(args)
        if not dates:
            return {"error": "End date can't be before start date!"}, 404

        args["start"] = dates.get("start")
        args["end"] = dates.get("end")
        res = []
        self.stat = args.get('stat')
        if not self.stat:
            return {"error": "No statistics found"}, 404
        if self.stat == "institutions":
            res = self.export_institutions(args)
        if self.stat == "users":
            res = self.export_users(args)
        if self.stat == "quartals" and self.institution_list:
            res = self.export_quartals(args)
        if self.stat == "quartals_by_org":
            res = self.export_quartals(args)
        if self.stat == "monthly_instances":
            res = self.export_monthly_instances(args)
        if not res:
            return {"error": "No statistics found"}, 404
        return res

    @auth.login_required
    @requires_admin
    def export_institutions(self, args=None):
        query = apply_rules_export_statistics("institutions", args)
        institutions = query.all()
        if not institutions:
            return []
        results = {}
        for inst in institutions:
            email = str(inst._email)
            domain = email.split("@")[1]

            if domain in results:
                results[domain] += 1
            else:
                results[domain] = 1
        results = sorted(results.items(), key=itemgetter(1), reverse=True)

        filter = args.get('filter')
        exclude = args.get('exclude')

        if filter is not None:
            res = []
            filter = filter.strip().split(',')
            if exclude:
                for item in results:
                    if item[0] not in filter:
                        res.append(item)
            else:
                for item in results:
                    if item[0] in filter:
                        res.append(item)
            if not res:
                return []
            data = {"data": res}
        else:
            if not results:
                return []
            data = {"data": results}
        return [data]

    @auth.login_required
    @requires_admin
    def export_users(self, args=None):
        query = apply_rules_export_statistics("users", args)
        users = query.all()
        if not users:
            return []
        results = []
        filter = args.get('filter')
        exclude = args.get('exclude')
        if filter is not None:
            filter = filter.strip().split(',')
            if exclude:
                for user in users:
                    email = str(user._email)
                    info = email.split("@")
                    obj = {
                        "user": info[0],
                        "institution": info[1]
                    }
                    if obj.get("institution") not in filter:
                        results.append(obj)
            else:
                for user in users:
                    email = str(user._email)
                    info = email.split("@")
                    obj = {
                        "user": info[0],
                        "institution": info[1]
                    }
                    if obj.get("institution") in filter:
                        results.append(obj)
        else:
            for user in users:
                email = str(user._email)
                info = email.split("@")
                obj = {
                    "user": info[0],
                    "institution": info[1]

                }
                results.append(obj)
        if not results:
            return []
        results = sorted(results, key=itemgetter('institution'))
        data = {"data": results}
        return [data]

    @auth.login_required
    @requires_admin
    def export_quartals(self, args=None):
        query = apply_rules_export_statistics("quartals", args)
        quartals = query.all()
        if not quartals:
            return []
        results = []
        filter = args.get("filter")
        if filter is not None:
            filter = filter.strip().split(",")
            exclude = args.get("exclude")
        stat = args.get("stat")
        # Assign quartals and institution type
        for row in quartals:
            email = str(row[0])
            domain = email.split("@")[1]
            date = row[1]

            if date is not None:
                month = int(date.strftime("%m"))
                year = date.strftime("%Y")

                if month in self.Q1:
                    q = 0
                elif month in self.Q2:
                    q = 1
                elif month in self.Q3:
                    q = 2
                elif month in self.Q4:
                    q = 3

                quartal = [0] * 4
                quartal[q] = 1

                if stat == "quartals":
                    org = self.set_institution_type(domain)
                    obj = {
                        "org": org,
                        "quartals": quartal,
                        "year": year
                    }
                if stat == "quartals_by_org":
                    obj = {
                        "org": domain,
                        "quartals": quartal,
                        "year": year
                    }

                if filter is not None:
                    if self.domain_filter(domain, filter, exclude):
                        results.append(obj)
                else:
                    results.append(obj)
        if not results:
            return []
        results = sorted(results, key=itemgetter('org', 'year'))
        last_item = {
            "org": None,
            "quartals": None,
            "year": None
        }

        # Combine results
        res = []
        for item in results:
            if last_item.get("org") is None:
                last_item = item
            else:
                if item.get("org") == last_item.get("org") and item.get("year") == last_item.get("year"):
                    item["quartals"] = self.list_sum(item["quartals"], last_item["quartals"])
                if item.get("org") == last_item.get("org") and item.get("year") > last_item.get("year"):
                    res.append(last_item)
                if item.get("org") != last_item.get("org"):
                    res.append(last_item)
                last_item = item
        res.append(last_item)

        dates = {'start': args.get('start'), 'end': args.get('end')}
        res = self.transform_empty(dates, res)
        data = {"data": res}
        return [data]

    @auth.login_required
    @requires_admin
    def export_monthly_instances(self, args=None):
        query = apply_rules_export_monthly_instances(args)
        instances = query.all()
        if not instances:
            return []
        results = {}

        for inst in instances:
            date = inst.provisioned_at

            if date is not None:
                date = date.date()
                y = date.strftime("%Y")
                m = date.month - 1
                if y not in results:
                    results[y] = [0] * (self.month_count + 1)
                results.get(y)[m] += 1
                results.get(y)[self.month_count] += 1
        if not results:
            return []
        dates = {'start': args.get('start'), 'end': args.get('end')}
        results = self.transform_empty(dates, results)
        data = {"data": results}
        return [data]

    def list_sum(self, a, b):
        return map(lambda x, y: x + y, a, b)

    def domain_filter(self, domain, filter, exclude):
        if exclude:
            if domain not in filter:
                return True
        else:
            if domain in filter:
                return True
        return False

    def set_institution_type(self, domain):
        if domain in self.institution_list.get("university"):
            org = "university"
        elif domain in self.institution_list.get("polytechnic"):
            org = "polytechnic"
        elif domain in self.institution_list.get("institution"):
            org = "institution"
        else:
            org = "na"
        return org

    def transform_empty(self, dates, cur):
        start_year = dates.get('start').strftime("%Y")
        start_month = int(dates.get('start').strftime("%m"))
        end_year = dates.get('end').strftime("%Y")
        end_month = int(dates.get('end').strftime("%m"))

        if start_month in self.Q1:
            sm = 0
            sq = 0
        elif start_month in self.Q2:
            sm = 3
            sq = 1
        elif start_month in self.Q3:
            sm = 6
            sq = 2
        elif start_month in self.Q4:
            sm = 9
            sq = 3

        if end_month in self.Q1:
            em = 3
            eq = 1
        elif end_month in self.Q2:
            em = 6
            eq = 2
        elif end_month in self.Q3:
            em = 9
            eq = 3
        elif end_month in self.Q4:
            em = 12
            eq = 4
        y = 0
        for year in cur:
            if self.stat == "monthly_instances":
                if year == start_year:
                    for i in range(sm):
                        cur[year][i] = ""
                if year == end_year:
                    for i in range(em, self.month_count):
                        cur[year][i] = ""
            if self.stat == "quartals" or self.stat == "quartals_by_org":
                if year.get('year') == start_year:
                    for i in range(sq):
                        cur[y]['quartals'][i] = ""
                if year.get('year') == end_year:
                    for i in range(eq, 4):
                        cur[y]['quartals'][i] = ""
            y += 1
        return cur

    def check_date_input(self, args=None):
        start = args.get('start')
        end = args.get('end')

        if start is None:
            start = str(dt(2000, 1, 1).date())
        if end is None:
            end = str(dt.utcnow().date())
        end = dt.strptime(end, self.date_format)
        start = dt.strptime(start, self.date_format)
        res = {}
        if end < start:
            return res
        res["start"] = start
        res["end"] = end
        return res
