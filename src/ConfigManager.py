import os
import time
import shutil
import logging
import pathlib
import threading
import ipaddress
import subprocess

import yaml
import jinja2
import requests
import watchdog.events
import watchdog.observers

import globals

class ConfigManagerException(Exception):
    pass

class ConfigManagerThread(threading.Thread):
    _configuration_directory: pathlib.Path
    _machines: dict[str, dict] = {}
    _interrupt_event = threading.Event()
    _file_change_observer = watchdog.observers.Observer()
    _do_shutdown = False
    _current_commit = ""

    def __init__(self, configuration_directory: pathlib.Path):
        super().__init__()
        if not self._check_path_permission(configuration_directory, directory=True):
            error_msg = f"Configuration directory '{configuration_directory}' is not accessible"
            logging.critical(error_msg)
            raise ConfigManagerException(error_msg)
        self._configuration_directory = configuration_directory

        event_handler = watchdog.events.PatternMatchingEventHandler(patterns=['*.y*l'], ignore_directories=True,
                                                                    case_sensitive=True)
        event_handler.on_modified = self._watchdog_reload
        event_handler.on_created = self._watchdog_reload
        event_handler.on_deleted = self._watchdog_reload
        event_handler.on_moved = self._watchdog_reload
        self._file_change_observer.schedule(event_handler, self._configuration_directory, recursive=True)

    def _watchdog_reload(self, reload_event: watchdog.events.FileModifiedEvent):
        logging.debug(f"File '{reload_event.src_path}' was {reload_event.event_type}")
        self.reload()

    @staticmethod
    def _get_latest_commit() -> tuple[bool, str]:
        git_repo = os.getenv("GIT_REPOSITORY")
        if git_repo is None:
            return False, "" # No repository is configured

        proc = subprocess.run(["git", "ls-remote", git_repo], capture_output=True)
        if proc.returncode != 0:
            error_msg = f"Could not get latest commit from '{git_repo}'. Reason {proc.stderr}"
            logging.error(error_msg)
            return False, ""

        # Extract commit hash from HEAD
        for line in proc.stdout.decode("utf-8").splitlines():
            if "\tHEAD" in line:
                return True, line.split("\t")[0]

        error_msg = f"Could not extract latest commit from '{git_repo}'"
        logging.error(error_msg)
        return False, ""

    def _clone_repository(self) -> bool:
        # clear configuration directory
        shutil.rmtree(self._configuration_directory)
        self._configuration_directory.mkdir(parents=True, exist_ok=True)

        # clone
        proc = subprocess.run(["git", "clone", "--depth", "1",
                               os.getenv("GIT_REPOSITORY"), self._configuration_directory], capture_output=True)
        if proc.returncode != 0:
            return False
        return True

    @property
    def machines(self) -> dict[str, dict]:
        return self._machines

    def get_machine_by_ip(self, ip_address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> dict:
        found_machine = {}
        for machine in self.machines.values():
            if machine.get(f"ipv{ip_address.version}") is None:
                continue
            if machine.get(f"ipv{ip_address.version}") == str(ip_address):
                found_machine = machine
                break
        return found_machine

    def reload(self):
        self._interrupt_event.set()

    def _run_git(self):
        while not self._do_shutdown:
            status, latest_commit = self._get_latest_commit()
            if not status:
                logging.error(f"Could not get latest commit. Keeping current configuration")
                time.sleep(10)
                continue
            if latest_commit == self._current_commit:
                logging.debug("No newer version of git repository. Keeping current configuration")
                time.sleep(10)
                continue
            else:
                self._current_commit = latest_commit

            # clone configured git repository
            status = self._clone_repository()
            if not status:  # cloning repository failed
                logging.error(f"Could not pull from configured git repository. Keeping current configuration")
                time.sleep(10)
                continue

            # parsing configuration from cloned repository
            status = self._parse_configuration_directory()
            if not status:
                logging.error(f"Could not read/parse current config from git. See previous messages. "
                              f"Keeping current configuration")
                time.sleep(10)
                continue

            logging.info(f"New configuration from commit '{self._current_commit}' with {len(self._machines)} "
                         f"machines successfully loaded")
            if len(self._machines) == 0:
                warning_msg = "No machines configured"
                logging.warning(warning_msg)

    def _run_local(self):
        logging.info(f"Using configuration from local directory: '{self._configuration_directory}'")
        self._file_change_observer.start()

        while not self._do_shutdown:
            status = self._parse_configuration_directory()
            if not status:
                error_msg = f"Could not read/parse current config. See previous messages. Keeping current configuration"
                logging.error(error_msg)
            else:
                logging.info(f"New configuration with {len(self._machines)} machines successfully loaded")

            if len(self._machines) == 0:
                warning_msg = "No machines configured"
                logging.warning(warning_msg)

            self._interrupt_event.wait()
            self._interrupt_event.clear()

        self._file_change_observer.stop()

    def run(self):
        logging.info("ConfigManagerThread started")
        status, commit_hash = self._get_latest_commit()
        if status:
            self._run_git()
        else:
            self._run_local()
        logging.info("ConfigManagerThread stopped")

    def stop(self):
        self._do_shutdown = True
        self.reload()

    @staticmethod
    def _check_path_permission(path: pathlib.Path, directory=False) -> bool:
        if not path.exists():
            error_msg = f"Path '{path}' does not exist"
            logging.error(error_msg)
            return False
        if not os.access(path, os.R_OK):
            error_msg = f"Path '{path}' is not readable"
            logging.error(error_msg)
            return False
        if directory:
            if not path.is_dir():
                error_msg = f"Path '{path}' is not a directory"
                logging.error(error_msg)
                return False
        return True

    def _read_yaml_file(self, path: pathlib.Path) -> tuple[bool, dict]:
        if not self._check_path_permission(path, directory=False):
            return False, {}
        with open(path, "r") as fd:
            content = fd.read()
            fd.close()
        try:
            yaml_content = yaml.safe_load(content)
        except yaml.YAMLError as e:
            error_msg = f"Could not load YAML file '{path}' caused by: '{e}'"
            logging.error(error_msg)
            return False, {}
        if yaml_content is None:
            return False, {}
        return True, yaml_content

    def _parse_configuration_directory(self) -> bool:
        if not self._check_path_permission(self._configuration_directory, directory=True):
            return False

        raw_configuration_data = []

        for directory_entry in sorted(self._configuration_directory.iterdir()):
            if directory_entry.suffix not in (".yml", ".yaml"):
                continue
            status, result = self._read_yaml_file(directory_entry)
            if not status:
                error_msg = f"Configuration file '{directory_entry}' is not readable or valid YAML"
                logging.error(error_msg)
                return False
            raw_configuration_data += result

        status, result = self._create_machines_from_configuration(raw_configuration_data)
        if not status:
            warning_msg = f"Error occurred while parsing configuration"
            logging.error(warning_msg)
            return False
        self._machines = result
        return True

    def _check_machine_configuration(self, config_entry: dict) -> tuple[bool, dict]:
        if config_entry.get("name") is None:
            error_msg = f"Configuration entry '{config_entry}' is missing 'name' attribute"
            logging.error(error_msg)
            return False, {}
        config_entry["name"] = config_entry["name"].lower()  # making names case-insensitive

        # check for IP addresses
        if "ipv4" not in config_entry.keys() and "ipv6" not in config_entry.keys():
            error_msg = f"Missing key 'ipv4' or 'ipv6' in '{config_entry}'"
            logging.error(error_msg)
            return False, {}
        else:
            try:
                if "ipv4" in config_entry.keys():
                    config_entry["ipv4"] = str(ipaddress.IPv4Address(config_entry["ipv4"]))
                if "ipv6" in config_entry.keys():
                    config_entry["ipv6"] = str(ipaddress.IPv6Address(config_entry["ipv6"]))
            except ipaddress.AddressValueError:
                error_msg = f"Configuration '{config_entry}' has at least one invalid IPv4/6 address"
                logging.error(error_msg)
                return False, {}

        # check if kickstart_template is readable
        if "kickstart_template" not in config_entry.keys():
            error_msg = f"Missing key 'kickstart_template' in '{config_entry}'"
            logging.error(error_msg)
            return False, {}

        kickstart_template_path = self._configuration_directory.joinpath(config_entry["kickstart_template"])
        if not self._check_path_permission(kickstart_template_path, directory=False):
            logging.error(f"Kickstart template '{kickstart_template_path}' is not readable")
            return False, {}
        config_entry["kickstart_template"] = str(kickstart_template_path.absolute())

        # check if os_arch is set
        if "os_arch" not in config_entry.keys():
            error_msg = f"Missing key 'os_arch' in '{config_entry}'"
            logging.error(error_msg)
            return False, {}
        os_arch = config_entry["os_arch"].lower()

        # check if os_version is set
        if "os_version" not in config_entry.keys():
            error_msg = f"Missing key 'os_version' in '{config_entry}'"
            logging.error(error_msg)
            return False, {}
        os_version = str(config_entry["os_version"]).lower()

        # check if os is set and available
        if "os" not in config_entry.keys():
            error_msg = f"Missing key 'os' in '{config_entry}'"
            logging.error(error_msg)
            return False, {}

        if config_entry["os"] not in globals.DISTRIBUTION_REPOS.keys():
            error_msg = f"Unknown distribution: '{config_entry['os']}'"
            logging.error(error_msg)
            return False, {}

        # check if repo is available
        os_repo_url = globals.DISTRIBUTION_REPOS[config_entry["os"].lower()].format(version=os_version,
                                                                              architecture=os_arch)
        config_entry["os_repo_url"] = os_repo_url
        try:
            check_repo_request = requests.get(f"{os_repo_url}/media.repo")
        except requests.exceptions.RequestException as e:
            error_msg = f"Could not request from: '{os_repo_url}/media.repo' due: '{e}'"
            logging.error(error_msg)
            return False, {}

        if check_repo_request.status_code != requests.codes.ok:
            error_msg = f"Release '{os_version}/{os_arch}' is not available inside repo '{os_repo_url}'"
            logging.error(error_msg)
            return False, {}

        return True, config_entry

    def _create_machines_from_configuration(self, raw_configuration: list[dict]) -> tuple[bool, dict]:
        machines = {}

        for entry in raw_configuration:
            # check for field 'name'
            name = entry.get("name")
            if name is None:
                error_msg = f"Missing field 'name' in '{entry}'"
                logging.error(error_msg)
                return False, {}

            # check for field 'spec'
            spec = entry.get("spec", {})
            if len(spec) == 0:
                error_msg = f"Missing field 'spec' in '{entry}'"
                logging.error(error_msg)
                return False, {}

            # check for field 'kind' and parse entry according to kind
            kind = entry.get("kind", "").lower()
            if kind == "machine":
                spec["name"] = name

                status, machine_spec = self._check_machine_configuration(spec)
                if not status:
                    error_msg = f"Invalid configuration detected in '{entry}'"
                    logging.error(error_msg)
                    return False, {}

                if machine_spec["name"] in machines:
                    error_msg = f"Duplicate machine '{machine_spec['name']}'"
                    logging.error(error_msg)
                    return False, {}
                machines[machine_spec["name"]] = machine_spec

            elif kind == "machinegroup":
                spec_machines = spec.get("machines", [])
                if len(spec_machines) == 0:
                    error_msg = f"Missing key 'machines' in '{entry}'"
                    logging.error(error_msg)
                    return False, {}

                # create machine_spec for each machine in machine group
                for machine in spec_machines:
                    machine_spec = spec.copy()
                    del machine_spec["machines"]
                    machine_spec.update(machine)

                    status, machine_spec = self._check_machine_configuration(machine_spec)
                    if not status:
                        error_msg = f"Invalid configuration detected in '{entry}'"
                        logging.error(error_msg)
                        return False, {}

                    if machine_spec["name"] in machines:
                        error_msg = f"Duplicate machine '{machine_spec['name']}'"
                        logging.error(error_msg)
                        return False, {}
                    machines[machine_spec["name"]] = machine_spec
            else:
                error_msg = f"Unknown or missing field 'kind' in '{entry}'"
                logging.error(error_msg)
                return False, {}

        # check for duplicate IPv4/6 addresses
        if not all((self._are_ips_unique(machines, 4), self._are_ips_unique(machines, 6))):
            logging.error("Duplicate IPs detected")
            return False, {}

        return True, machines

    @staticmethod
    def _are_ips_unique(machines: dict[str, dict], version: int) -> bool:
        ips = []
        for machine in machines.values():
            machine_ip = machine.get(f"ipv{version}")
            if machine_ip is None:
                continue
            if machine_ip in ips:  # duplicate found
                error_msg = f"Duplicate IPv{version} address '{machine_ip}' in machine '{machine['name']}'"
                logging.error(error_msg)
                return False
            ips.append(machine_ip)
        return True

    def generate_kickstart(self, machine: dict) -> tuple[bool, str]:
        if not self._check_path_permission(pathlib.Path(machine["kickstart_template"]), directory=False):
            return False, "Specified kickstart template does not exist or is not readable"

        with open(machine["kickstart_template"], "r") as fd:
            template_file_content = fd.read()
            fd.close()

        template = jinja2.Template(template_file_content)

        machine["hostname"] = machine["name"]
        kickstart_data = template.render(**machine)
        return True, kickstart_data
