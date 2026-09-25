# Bootique

*A boutique for booting machines over the network uniquely*

Der HTTP-Server liefert für jede anfordernde Maschine ein eigenes iPXE-Bootmenü und eine eigene Kickstart-Datei aus, sodass die Installation automatisiert durchgeführt werden kann.

Bootique identifiziert die anfordernde Maschine anhand der Source-IP, von der der Request abgesetzt wird. Befindet sich der Host hinter einem NAT, kann alternativ auch die MAC-Adresse verwendet werden.

## Voraussetzungen

Das Booten über das Netzwerk erfordert einen DHCP- und einen TFTP-Server. Diese müssen zunächst installiert und so konfiguriert werden, dass dem anfordernden Host die richtige IP-Adresse zugewiesen wird. Außerdem müssen die `client-classes` entsprechend konfiguriert sein. Hier ein Beispiel für den Kea-DHCP-Server:

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

Bootique läuft als Container und kann mittels **Quadlet** direkt über *systemd* verwaltet werden. Dazu muss lediglich `podman` auf der Maschine installiert sein. Anschließend werden die folgenden **Quadlet**-Dateien unter `/etc/containers/systemd/` erstellt:

```ini
# /etc/containers/systemd/bootique.image

[Image]
Creds=<Container Registry Credentials> # Kann weggelassen werden, wenn keine Authentifizierung erforderlich ist
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
# Volume=/opt/bootique:/data/config:ro  # Wenn die Konfiguration nicht über Git bezogen werden soll
Network=host
Environment=GIT_REPOSITORY=https://git.example.com/bootique-config.git # Wenn nicht angegeben, wird die lokale Konfiguration verwendet
Environment=BASE_URL=http://netboot.example.com # Origin-Teil der URL, über die der HTTP-Server aus Sicht der zu installierenden Maschinen erreichbar ist
Environment=IS_BEHIND_PROXY=true # Verwendet den X-Forwarded-For-Header zur Ermittlung der Source-IP

# Setzt die Repository-URL. Jede Umgebungsvariable, die mit 'REPO_' beginnt, erstellt einen OS-Eintrag.
# Wird beispielsweise in der Maschinenkonfiguration 'os: rocky' angegeben, wird das folgende Repository verwendet.
# Die Parameter 'version' und 'architecture' werden durch 'os_version' bzw. 'os_arch' ersetzt.
Environment=REPO_ROCKY=https://download.rockylinux.org/pub/rocky/{version}/BaseOS/{architecture}/os/

# Repository für CentOS
Environment=REPO_CENTOS=https://vault.centos.org/{version}/BaseOS/{architecture}/os/

[Service]
Restart=always

[Install]
WantedBy=multi-user.target
```

Danach müssen die **Quadlet**-Dateien nur noch mittels `systemctl daemon-reload` von *systemd* neu eingelesen werden. Anschließend kann der Service mit `systemctl status bootique.service` überprüft werden.

## Konfiguration

Maschinen werden in YAML-Dateien deklariert und konfiguriert. Deren Aufbau ähnelt dem eines Kubernetes-Manifests. Hier ein Beispiel:

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
  name: store-machines # Wird in der Konfiguration nicht verwendet, muss aber trotzdem angegeben werden
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

ℹ️ Die Felder `name`, `ipv4` bzw. `ipv6`, `kickstart_template`, `os`, `os_version` und `os_arch` sind erforderlich.

Bei `MachineGroup`-Deklarationen ist zu beachten, dass die maschinenspezifische Konfiguration die übergeordnete Konfiguration überschreibt.

Im oben gezeigten Beispiel verwendet `store1.example.com` das auf Gruppenebene definierte Kickstart-Template unter `templates/default.ks.j2`. Der Wert des Keys `selinux` ist `False`.

Bei der Maschine `store2.example.com` wird `selinux` hingegen auf `True` gesetzt und stattdessen `templates/store2.ks.j2` als Kickstart-Template verwendet.

### Templating

Die Stärke von Bootique liegt in seiner Templating-Funktionalität. Damit lassen sich praktisch beliebige Kickstart-Dateien erstellen. Bootique verwendet im Hintergrund Jinja als Templating-Engine.

Der unter `kickstart_template` angegebene Pfad zum Template ist relativ zum Root-Verzeichnis der Konfiguration. Templates müssen daher nicht im Verzeichnis `templates/` liegen, sondern können beispielsweise auch im selben Verzeichnis wie die Maschinenkonfigurationen abgelegt werden.

Bootique sucht ausschließlich im Root-Verzeichnis der Konfiguration nach YAML-Dateien. Bei Bedarf kann diese Funktionalität zukünftig erweitert werden, sodass YAML-Dateien auch in Unterverzeichnissen organisiert werden können.

Zusammengefasst kann die Verzeichnisstruktur der Konfiguration beispielsweise wie folgt aussehen:

```text
.
├── machines.yaml
├── other_machines
│   └── test.yaml # <- Wird nicht berücksichtigt
└── templates
    ├── default.ks.j2
    └── store2.ks.j2
```

#### Vordefinierte Variablen im Template

Die in der Konfiguration definierten Keys können beliebig innerhalb der Templates verwendet werden. Dadurch gibt es bei der Gestaltung der Konfiguration und der Templates kaum Einschränkungen.

Folgende Variablen stehen standardmäßig im Template zur Verfügung und sollten daher nicht in der Konfiguration gesetzt werden:

- `hostname`: Enthält denselben Wert wie `name` in der Konfiguration.
- `os_repo_url`: Enthält die vollständige URL zum Repository. Diese wird aus den Parametern `os`, `os_version` und `os_arch` der Konfiguration zusammengesetzt.

#### Template-Gestaltung

Das gerenderte Template sollte eine valide Kickstart-Datei ergeben. Bootique überprüft jedoch nicht, ob die erzeugte Kickstart-Datei syntaktisch korrekt ist. Die Syntax kann mit dem Befehl `ksvalidate` überprüft werden. Die vollständige Semantik der Konfiguration lässt sich damit jedoch nicht validieren.

Letztendlich kann selbst entschieden werden, ob für jede Maschine ein eigenes Template angelegt oder mithilfe von Jinja ein möglichst generisches Template erstellt wird. Dabei sollte ein guter Kompromiss gefunden werden, damit die Wartbarkeit nicht darunter leidet.

Hier ein Beispiel für das Template `default.ks.j2`:

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

### Konfigurationsupdates

Bootique verarbeitet neue Konfigurationen während der Laufzeit. Ein Neustart ist daher nicht erforderlich.

Wird Bootique ohne ein gültiges, über die Umgebungsvariable `GIT_REPOSITORY` angegebenes Git-Repository gestartet, wird die lokale Konfiguration unter `/data/config/` verwendet. Dieser Pfad kann über die Umgebungsvariable `CONFIG_DIRECTORY` geändert werden.

Bei Verwendung einer lokalen Konfiguration setzt Bootique einen File-Event-Handler auf das Konfigurationsverzeichnis und lädt die Konfiguration nach jeder Änderung neu.

Bezieht Bootique die Konfiguration aus einem Git-Repository, wird alle 10 Sekunden überprüft, ob ein neuer Commit im Repository vorhanden ist. Ist dies der Fall, klont Bootique das aktualisierte Repository und versucht anschließend, die neue Konfiguration einzulesen.

Unabhängig von der verwendeten Konfigurationsmethode gilt: Kann eine neue Konfiguration nicht erfolgreich eingelesen werden, wird die bisherige Konfiguration weiterhin verwendet. Erst nachdem eine neue Konfiguration erfolgreich validiert und eingelesen wurde, ersetzt sie die bisherige Konfiguration.

## Starten

Nachdem `bootique.service` angelegt und die Konfiguration erstellt wurde, kann Bootique wie gewohnt mit folgendem Befehl gestartet werden:

```bash
systemctl start bootique.service
```

Wenn alles funktioniert, sollte im Log eine Ausgabe ähnlich der folgenden erscheinen:

```text
[2025-05-31 13:25:44 +0000] [4] [INFO] Starting gunicorn 23.0.0
[2025-05-31 13:25:44 +0000] [4] [INFO] Listening at: http://0.0.0.0:443 (4)
[2025-05-31 13:25:44 +0000] [4] [INFO] Using worker: sync
[2025-05-31 13:25:44 +0000] [5] [INFO] Booting worker with pid: 5
{"time": "2025-05-31T13:25:44+0000", "level": "INFO", "message": "ConfigManagerThread started", "function": "run", "module": "ConfigManager"}
{"time": "2025-05-31T13:25:45+0000", "level": "INFO", "message": "New configuration from commit '7fbbcb616689e2067468b5c17bac585a831fafc0' with 3 machines successfully loaded", "function": "_run_git", "module": "ConfigManager"}
```

## Troubleshooting

Bootique stellt mehrere HTTP-Endpunkte zur Verfügung, über die die aktuelle Konfiguration abgefragt werden kann:

- `/admin/machines`: Liefert alle in Bootique konfigurierten Maschinen.
- `/admin/machines/<machine_name>`: Liefert die Konfiguration der über `machine_name` angegebenen Maschine.
- `/kickstart`: Liefert die gerenderte Kickstart-Datei zurück. Ohne Query-Parameter wird die Kickstart-Datei für die Source-IP des Requests ausgeliefert. Um die Kickstart-Datei einer bestimmten Maschine abzurufen, kann `?ip=<requested_ip>` als Query-Parameter angegeben werden. Alternativ kann `?mac=<requested_mac>` verwendet werden, sofern für die deklarierte Maschine eine MAC-Adresse hinterlegt wurde. Dies ist insbesondere erforderlich, wenn sich die anfordernde Maschine hinter einem NAT befindet.

✨ Happy Installing ✨