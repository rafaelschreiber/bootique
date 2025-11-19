import os
import logging
import ipaddress

import flask

import globals

admin_blueprint = flask.Blueprint('admin', __name__)

@admin_blueprint.before_request
def admin_before_request():
    logging.info(f"{flask.request.method} {flask.request.path} from {flask.request.remote_addr}",
                 extra=dict(method=flask.request.method, path=flask.request.path,
                            remote_addr=flask.request.remote_addr)
                 )

@admin_blueprint.route("/machines", methods=['GET'])
def get_machines():
    if flask.request.args.get("ip") is None:
        return flask.jsonify(globals.CONFIGMANAGER.machines)
    else:
        try:
            ip = ipaddress.ip_address(flask.request.args.get("ip"))
        except ValueError:
            return "Bad request", 400

        return flask.jsonify(globals.CONFIGMANAGER.get_machine_by_ip(ip))

@admin_blueprint.route("/machines/<machine_name>", methods=['GET'])
def get_machine(machine_name: str):
    return flask.jsonify(globals.CONFIGMANAGER.machines.get(machine_name.lower(), {}))