import logging
import os
import pathlib
# import threading

import flask
import pythonjsonlogger

import globals
import ConfigManager
import routes
# import tftp

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

    # Optional: Disable info messages from fbtftp base_handler module
    logging.getLogger("fbtftp").setLevel(logging.WARNING)


def setup():
    setup_logging()
    globals.CONFIGMANAGER = ConfigManager.ConfigManagerThread(pathlib.Path(os.getenv("CONFIG_DIRECTORY",
                                                                                     "/data/config")))
    globals.CONFIGMANAGER.start()

    APP.register_blueprint(routes.kickstart_blueprint, url_prefix="/kickstart")
    APP.register_blueprint(routes.admin_blueprint, url_prefix="/admin")
    APP.register_blueprint(routes.bootmenu_blueprint, url_prefix="/pxe")

    # globals.TFTP_SERVER = tftp.TFTPServer(globals.TFTP_CONFIGURATION["address"],
    #                                       globals.TFTP_CONFIGURATION["port"],
    #                                       globals.TFTP_CONFIGURATION["retries"],
    #                                       globals.TFTP_CONFIGURATION["timeout"])

    # tftp_server_thread = threading.Thread(target=globals.TFTP_SERVER.run)
    # tftp_server_thread.start()


# entrypoint
setup()
if __name__ == "__main__":
    APP.run(debug=True, port=8080)
