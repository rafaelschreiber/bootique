import logging
import ipaddress

import flask

import globals

kickstart_blueprint = flask.Blueprint('kickstart', __name__)

@kickstart_blueprint.before_request
def kickstart_before_request():
    logging.info(f"{flask.request.method} {flask.request.path} from {flask.request.remote_addr}",
                 extra=dict(method=flask.request.method, path=flask.request.path,
                            remote_addr=flask.request.remote_addr)
                 )

@kickstart_blueprint.route("/", methods=['GET'])
def get_kickstart_file():
    if flask.request.headers.get('X-Forwarded-For') is not None:
        requester_ip = flask.request.headers.get('X-Forwarded-For').split(',')[0].strip()
    elif flask.request.args.get("ip") is not None:
        requester_ip = flask.request.args.get("ip")
    else:
        requester_ip = flask.request.remote_addr

    try:
        requester_ip = ipaddress.ip_address(requester_ip)
    except ValueError:
        return "Bad request", 400

    machine = globals.CONFIGMANAGER.get_machine_by_ip(requester_ip)
    if not machine:
        return "Not Found", 404

    status, kickstart = globals.CONFIGMANAGER.generate_kickstart(machine)
    if not status:
        return
    return flask.Response(kickstart, mimetype='text/plain'), 200
