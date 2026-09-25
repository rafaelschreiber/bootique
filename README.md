# Bootique
*A boutique for booting machines over the network uniquely*

The HTTP server provides a custom iPXE boot menu and Kickstart file for each requesting machine, allowing the installation to be performed automatically.

Bootique identifies requesting machines based on the source IP address from which the request originates. Alternatively, if the host's IP address is behind NAT, the MAC address can be used.

## Requirements

Booting over the network requires a DHCP server and a TFTP server. These must be installed first, and the correct IP address must be assigned to the requesting host. In addition, the `client-classes` must be configured correctly.

Here is an example for the Kea DHCP server:

```json
"client-classes": [
    {
        "name": "defaults",
        "test": "1 == 1",
        "next-server": "netboot.example.com"
    },
    {
        "name": "pxe-bios",
        "test": "not member('ipxe') and option[93].hex == 0x0000",
        "boot-file-name": "undionly.kpxe"
    },
    {
        "name": "pxe-uefi",
        "test": "not member('ipxe') and not member('pxe-bios')",
        "boot-file-name": "ipxe.efi"
    }
]
```

## Installation

Bootique runs as a container and can be managed directly through *systemd* using **Quadlet**. Only `podman` needs to be installed on the machine, and the following **Quadlet** files must be created under `/etc/containers/systemd/`:

```ini
# /etc/containers/systemd/bootique.image

[Image]
Creds=<Container Registry Credentials> # Can be omitted if authentication is not required
Image=registry.example.com/bootique:latest
```

```ini
# /etc/containers/systemd/bootique.container

[Unit]
Description=Bootique Network Boot
After=local-fs.target

[Container]
Image=registry.example.com/bootique:latest
Pull=always
# Volume=/opt/bootique:/data/config:ro  # If the configuration should not be obtained via Git
Network=host
Environment=GIT_REPOSITORY=https://git.example.com/bootique-config.git  # If not specified, the local configuration is used
Environment=BASE_URL=http://netboot.example.com  # Origin part of the URL through which the HTTP server is reachable from the machines being installed
Environment=IS_BEHIND_PROXY=true # Uses the X-Forwarded-For header to determine the source IP
# Sets the repository URL. Every environment variable starting with 'REPO_' creates an OS entry.
# In this case, when 'os: rocky' is specified in the machine configuration, the following repository is used.
# The parameters 'version' and 'architecture' are substituted with 'os_version' and 'os_arch' respectively.
Environment=REPO_ROCKY=https://download.rockylinux.org/pub/rocky/{version}/BaseOS/{architecture}/os/
# Here for CentOS
Environment=REPO_CENTOS=https://vault.centos.org/{version}/BaseOS/{architecture}/os/
```

[Service]
Restart=always

[Install]
WantedBy=multi-user.target
```

Afterwards, *systemd* only needs to reload the **Quadlet** files using `systemctl daemon-reload`. The service can then be checked with `systemctl status bootique.service`.

## Configuration

Machines are declared and configured in YAML files. Their structure is similar to Kubernetes manifests.

Here is an example:

```yaml
# machines.yaml

- kind: Machine
  name: core.example.com
  spec:
    kickstart_template: templates/default.ks.j2
    os: centos
    os_version: 8
    os_arch: x86_64
    ipv4: 10.0.0.1
    ipv4_gw: 10.0.0.254
    ipv4_mask: 255.255.255.0

- kind: MachineGroup
  name: store-machines # Not used in the configuration, but must still be specified
  spec:
    kickstart_template: templates/default.ks.j2
    os: rocky
    os_version: 9
    os_arch: x86_64
    ipv4_gw: 10.0.1.254
    ipv4_mask: 255.255.255.0
    selinux: False
    machines:
      - name: store1.example.com
        ipv4: 10.0.1.1
        swap_size: 4096
      - name: store2.example.com
        ipv4: 10.0.1.2
        kickstart_template: templates/store2.ks.j2
        selinux: True
```

ℹ️ The fields `name`, `ipv4` or `ipv6`, `kickstart_template`, `os`, `os_version`, and `os_arch` are required.

For `MachineGroup` declarations, it is important to know that machine-specific configuration overrides the configuration defined at the group level.

In the example above, `store1.example.com` uses the globally defined Kickstart template at `templates/default.ks.j2`, and the `selinux` key is set to `False`.

For `store2.example.com`, `selinux` is set to `True`, and `templates/store2.ks.j2` is used instead.

### Templating

The strength of Bootique lies in its templating functionality. It makes it possible to create virtually any kind of Kickstart file. Bootique uses Jinja as its templating engine.

The path specified in `kickstart_template` is relative to the root directory of the configuration. Templates therefore do not have to reside in the `templates/` directory; they can also be located in the same directory as the machine configuration files.

Bootique only searches for YAML files in the root directory of the configuration. If necessary, this functionality can be extended in the future to allow YAML files to be organized in subdirectories.

In summary, the configuration directory structure looks like this:

```text
.
├── machines.yaml
├── other_machines
│   └── test.yaml # <- Will not be considered
└── templates
    ├── default.ks.j2
    └── store2.ks.j2
```

#### Predefined Template Variables

The keys defined in the configuration can be used freely within templates. This means there are virtually no limits when designing configurations and templates.

The following variables are available in templates by default and should not be set in the configuration:

- `hostname`: Contains the same value as `name` in the configuration.
- `os_repo_url`: The full URL to the OS repository. It is constructed from the `os`, `os_version`, and `os_arch` parameters in the configuration.

#### Template Design

The rendered template should ultimately produce a valid Kickstart file. However, Bootique does not check whether the generated Kickstart file is syntactically correct. Its syntax can be validated using the `ksvalidate` command. The overall semantics, however, cannot be validated automatically.

Ultimately, you can decide whether to create a separate template for every machine or use Jinja to make the templates as generic as possible. A good compromise should be found so that maintainability does not suffer.

Here is an example of the `default.ks.j2` template:

```jinja
# templates/default.ks.j2

lang en_US.UTF-8 --addsupport=de_AT.UTF-8,de_DE.UTF-8
keyboard --xlayouts='de (nodeadkeys)'
timezone Europe/Vienna --utc

# Network configuration
network --bootproto=static --device=ens192 --gateway={{ ipv4_gw }} --ip={{ ipv4 }} --nameserver={{ ipv4_gw }} --netmask={{ ipv4_mask }} --ipv6=auto --activate --ipv4-dns-search=example.com --hostname={{ hostname }}

# Installation source
url --url={{ os_repo_url }}/os/

reboot
text

clearpart --all --initlabel

# System Partitions, VolumeGroups and Logical Volumes
part /boot --fstype="xfs" --ondisk=/dev/sda --size=2048
part /boot/efi --fstype="efi" --ondisk=/dev/sda --size=100 --fsoptions="umask=0077,shortname=winnt"
part pv.00 --fstype="lvmpv" --ondisk=/dev/sda --grow
volgroup BootDisk --pesize=4096 pv.00
logvol swap --fstype="swap" --size={{ swap_size | default(1024) }} --name=swap --vgname=BootDisk
logvol / --fstype="xfs" --grow --name=root --vgname=BootDisk

%packages
@^minimal-environment
@standard

bash-completion
bind-utils
bzip2
glibc-headers
grubby

[...]

# Update bootloader configuration to enable/disable SELinux
%post
/usr/sbin/grubby --update-kernel ALL --args selinux={{ selinux | default(True) | int }}
%end
```

### Configuration Updates

Bootique parses new configuration while running, so a restart is not required.

If Bootique is started without a valid Git repository specified through the `GIT_REPOSITORY` environment variable, the local configuration under `/data/config/` is used. This path can be changed using the `CONFIG_DIRECTORY` environment variable.

When using local configuration, Bootique sets up a file event handler on the directory and reloads the configuration whenever a change is detected.

When Bootique obtains its configuration from a Git repository, it checks every 10 seconds whether a new commit is available in the repository. If a new commit is detected, Bootique clones the updated repository and attempts to parse the new configuration.

Regardless of which configuration method is used, if a new configuration cannot be loaded successfully, the previous configuration remains active. It is only replaced once a valid new configuration has been loaded.

## Starting Bootique

Once `bootique.service` has been created and the configuration is in place, Bootique can be started as usual with:

```bash
systemctl start bootique.service
```

If everything is working correctly, the log should contain output similar to the following:

```text
[2025-05-31 13:25:44 +0000] [4] [INFO] Starting gunicorn 23.0.0
[2025-05-31 13:25:44 +0000] [4] [INFO] Listening at: http://0.0.0.0:443 (4)
[2025-05-31 13:25:44 +0000] [4] [INFO] Using worker: sync
[2025-05-31 13:25:44 +0000] [5] [INFO] Booting worker with pid: 5
{"time": "2025-05-31T13:25:44+0000", "level": "INFO", "message": "ConfigManagerThread started", "function": "run", "module": "ConfigManager"}
{"time": "2025-05-31T13:25:45+0000", "level": "INFO", "message": "New configuration from commit '7fbbcb616689e2067468b5c17bac585a831fafc0' with 3 machines successfully loaded", "function": "_run_git", "module": "ConfigManager"}
```

## Troubleshooting

Bootique provides several HTTP endpoints that can be used to inspect its configuration:

- `/admin/machines`: Returns all machines configured in Bootique.
- `/admin/machines/<machine_name>`: Returns the configuration for the `machine_name` specified in the path.
- `/kickstart`: Returns the rendered Kickstart file. Without query parameters, it returns the Kickstart file associated with the source IP address of the request. To retrieve the Kickstart file for a specific machine, specify `?ip=<requested_ip>` in the request. Alternatively, `?mac=<requested_mac>` can be used if the declared machine has a MAC address assigned. This is particularly useful when the requesting machine is located behind NAT.

✨ Happy Installing ✨