import datetime
import ipaddress
import logging
import os

import flask
import jinja2
import yaml

import globals

bootmenu_blueprint = flask.Blueprint('bootmenu', __name__)
TEMPLATE_ENV = jinja2.Environment(loader=jinja2.FileSystemLoader("templates/"))

def multiline_output_ipxe(text: str) -> str:
    multiline_output = "set space:hex 20\n"  # set variable to create whitespaces
    text_lines = text.splitlines()

    # used to count percentage of configuration show as with 'more' command
    num_lines = len(text_lines)
    break_count = 0
    ipxe_rows = 23

    for count, line in enumerate(text_lines, start=1):
        multiline_output += f"echo -- {line.replace(' ', "${space:string}")}\n"
        if count % ipxe_rows == 0:
            break_count += 1
            if int(ipxe_rows * break_count / num_lines * 100) == 100:
                multiline_output += "echo -n -- ${hex:0d}\n"
                break
            multiline_output += (
                f"prompt --key 0x20 -- --MORE-- ({int(ipxe_rows * break_count / num_lines * 100)}%)\n"
                f"echo -n -- ${{hex:0d}}\n")
    multiline_output += "prompt --key 0x20 -- --END-- (100%)\n"

    return multiline_output


def render_config_menu(machine: dict):
    yaml_config = yaml.safe_dump(machine, default_flow_style=False, sort_keys=True)
    return multiline_output_ipxe(yaml_config)


def render_kickstart_menu(machine: dict):
    status, kickstart = globals.CONFIGMANAGER.generate_kickstart(machine)
    if not status:
        kickstart = "Failed to generate kickstart\n" + kickstart
    return multiline_output_ipxe(kickstart)


@bootmenu_blueprint.before_request
def bootmenu_before_request():
    logging.info(f"{flask.request.method} {flask.request.path} from {flask.request.remote_addr}",
                 extra=dict(method=flask.request.method, path=flask.request.path,
                            remote_addr=flask.request.remote_addr)
                 )

@bootmenu_blueprint.route("/bootmenu.ipxe", methods=['GET'])
def get_bootmenu_file():
    if flask.request.args.get("ip") is not None:
        requester_ip = flask.request.args.get("ip")
    elif flask.request.headers.get('X-Forwarded-For') is not None:
        requester_ip = flask.request.headers.get('X-Forwarded-For').split(',')[0].strip()
    else:
        requester_ip = flask.request.remote_addr

    machine = globals.CONFIGMANAGER.get_machine_by_ip(ipaddress.ip_address(requester_ip))
    if machine:  # machine found
        machine = machine.copy()
        machine["echo_configuration"] = render_config_menu(machine)
        machine["echo_kickstart"] = render_kickstart_menu(machine)
        machine["ip_address"] = requester_ip
        machine["time_generated"] = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d %H:%M:%S")
        machine["origin"] = os.getenv("SELF_SERVER_ORIGIN", "http://localhost:80")
        data = TEMPLATE_ENV.get_template("bootique-menu.ipxe.j2").render(**machine)
    else:  # machine not found
        data = TEMPLATE_ENV.get_template("bootique-notfound.ipxe.j2").render(
            ip_address=requester_ip,
            time_generated=datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d %H:%M:%S"),
        )
    return flask.Response(data, mimetype='text/plain'), 200
