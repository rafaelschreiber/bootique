import logging
import os
import pathlib

import flask
import pythonjsonlogger
import werkzeug.middleware.proxy_fix

import globals
import ConfigManager
import routes

APP = flask.Flask(__name__)


def setup_logging():
    handler = logging.StreamHandler()
    formatter = pythonjsonlogger.json.JsonFormatter(
        fmt='%(asctime)s %(levelname)s %(message)s %(funcName)s %(module)s',
        datefmt='%Y-%m-%dT%H:%M:%S%z',
        rename_fields={"levelname": "level", "funcName": "function", "asctime": "time"}
    )
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers = [handler]

    # Optional: ensure Flask's own logger uses JSON too
    logging.getLogger('werkzeug').handlers = [handler]


def setup():
    setup_logging()
    globals.CONFIGMANAGER = ConfigManager.ConfigManagerThread(pathlib.Path(os.getenv("CONFIG_DIRECTORY",
                                                                                     "/data/config")))
    globals.CONFIGMANAGER.start()

    # Recognise X-Forwarded-For Header as source IP when behind a proxy
    if os.getenv("IS_BEHIND_PROXY", "false").lower() == "true":
        APP.wsgi_app = werkzeug.middleware.proxy_fix.ProxyFix(
            APP.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1
        )

    APP.register_blueprint(routes.kickstart_blueprint, url_prefix="/kickstart")
    APP.register_blueprint(routes.admin_blueprint, url_prefix="/admin")
    APP.register_blueprint(routes.pxe_blueprint, url_prefix="/pxe")


# entrypoint
setup()
if __name__ == "__main__":
    APP.run(debug=True, port=8080)
