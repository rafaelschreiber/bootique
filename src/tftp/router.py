import ipaddress
import logging
import pathlib
import datetime

import yaml
import jinja2

import globals

class TFTPRouter:
    template_env = jinja2.Environment(loader=jinja2.FileSystemLoader("templates/"))

    _address: str
    _port: int
    _file: str

    def __init__(self, address: str, port: int, file: str) -> None:
        self._address = address
        self._port = port
        self._file = file

    @staticmethod
    def _read_file_binary(file_path: pathlib.Path) -> tuple[bool, bytes]:
        try:
            with open(file_path, "rb") as fd:
                content = fd.read()
                fd.close()
        except (FileNotFoundError, PermissionError) as e:
            error_msg = f"Unable to read file {file_path.absolute()}: {e}"
            logging.error(error_msg)
            return False, b''
        return True, content

    @staticmethod
    def _multiline_output_ipxe(text: str) -> str:
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

    def _render_config_menu(self, machine: dict):
        yaml_config = yaml.safe_dump(machine, default_flow_style=False, sort_keys=True)
        return self._multiline_output_ipxe(yaml_config)

    def _render_kickstart_menu(self, machine: dict):
        status, kickstart = globals.CONFIGMANAGER.generate_kickstart(machine)
        if not status:
            kickstart = "Failed to generate kickstart\n" + kickstart
        return self._multiline_output_ipxe(kickstart)

    def _render_ipxe_bootmenu(self) -> tuple[bool, str]:
        machine = globals.CONFIGMANAGER.get_machine_by_ip(ipaddress.ip_address(self._address))
        if machine:  # machine found
            machine = machine.copy()
            machine["echo_configuration"] = self._render_config_menu(machine)
            machine["echo_kickstart"] = self._render_kickstart_menu(machine)
            machine["ip_address"] = self._address
            machine["time_generated"] = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d %H:%M:%S")
            machine["origin"] = os.getenv("SELF_SERVER_ORIGIN", "http://localhost:80")
            data = self.template_env.get_template("bootique-menu.ipxe.j2").render(**machine)
        else:  # machine not found
            data = self.template_env.get_template("bootique-notfound.ipxe.j2").render(
                ip_address=self._address,
                time_generated=datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d %H:%M:%S"),
            )
        return True, data

    def _generate_return_data(self) -> tuple[bool, str | bytes]:
        if self._file.lower() in ("undionly.kpxe", "ipxe.efi"):
            status, data = self._read_file_binary(pathlib.Path(f"static/{self._file.lower()}"))
        elif self._file.lower() in ("bootique.ipxe", "openshift-bootstrap.ipxe"):
            status, data = self._render_ipxe_bootmenu()
        else:
            status, data = (False, b'')
        return status, data

    @property
    def return_data(self) -> tuple[bool, bytes]:
        status, data = self._generate_return_data()
        if isinstance(data, str):
            data = data.encode("ascii")
        return status, data
