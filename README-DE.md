# Bootique
*A boutique for booting machines over the network uniquely*

Der HTTP-Server liefert eine für die anforderne Maschine eigenes iPXE-Bootmenu und Kickstart-Datei aus, damit die Installation automatisiert durchgeführt werden kann.

Bootique identifiziert die anfordernde Maschinen anhand der Source-IP mit der der Rechner den Request absetzt. Alternativ, falls die IP des Hosts hinter einem NAT ist, kann auch die MAC-Adresse
verwendet werden.

## Voraussetzungen
Das Booten übers Netzwerk erfordert einen DHCP- und einen TFTP-Server. Dieser muss zuerst installiert sein und die richtige IP-Adresse für den anfordernden Host vergeben. Außerdem müssen die `client-classes` richtig konfiguriert sein. Hier ein Beispiel für den Kea DHCP-Server:

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
Bootique läuft als Container und kann mittels *Quadlet* direkt über *systemd* gemanaged werden. Dazu muss nur `podman` auf der Maschine installiert und folgende *Quadlet*-Dateien unter `/etc/containers/systemd/` erstellt werden:

```ini
# /etc/containers/systemd/bootique.image

[Image]
Creds=<Container Registry Credentials> # kann weggelassen werden, wenn keine Authentifizierung notwendig ist
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
# Volume=/opt/bootique:/data/config:ro  # wenn die Konfiguration nicht über Git bezogen werden soll
Network=host
Environment=GIT_REPOSITORY=https://git.example.com/bootique-config.git  # wenn nicht spezifiziert wird die lokale Konfiguration hergenommen.
Environment=BASE_URL=http://netboot.example.com # origin teil der URL worüber der HTTP server aus Sicht der zu installiernden Maschinen erreichbar ist 
Environment=IS_BEHIND_PROXY=true. # Verwendet X-Forwarded-For-Header zur ermittlung der Source-IP
# Setzt die Repository-URL. Jetzt Umgebungsvariable startend mit 'REPO_' erstellt einen os-Eintrag. In diesem Fall, wenn als 'os: rocky' angegeben wird,
# wird das folgende Repo verwendet. Die Parameter 'version' und 'architecture' werden mit 'os_version' und 'os_arch' substituiert.
Environment=REPO_ROCKY=https://download.rockylinux.org/pub/rocky/{version}/BaseOS/{architecture}/os/
# Hier für CentOS
Environment=REPO_CENTOS=https://vault.centos.org/{version}/BaseOS/{architecture}/os/

[Service]
Restart=always

[Install]
WantedBy=multi-user.target
```

Danach müssen die *Quadlet*-Files nur mehr von *systemd* mittels `systemctl daemon-reload` neu eingelesen werden. Mit `systemctl status bootique.service` kann nun der Service überprüft werden.

## Konfiguration
Maschinen werden in YAML-Dateien deklariert und konfiguriert. Diese ähneln dem Aufbau eines Kubernetes Manifests. Hier ein Beispiel:

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

ℹ️ Die Felder `name`, `ipv4` || `ipv6`, `kickstart_template`, `os`, `os_version` und `os_arch` sind erforderlich.

Bei `MachineGroup`-Deklarationen ist es wichtig zu wissen, dass die Maschinenspezifische Konfiguration die überliegende überschreibt. 

Im oben gezeigten Beispiel verwendet die `store1.example.com` das global definierte Kickstart-Template unter `templates/default.ks.j2` und der Key `selinux` ist `False`.<br>
Bei der Maschine `store2.example.com` ist `selinux` auf `True` gesetzt und `templates/store2.ks.j2` wird stattdessen verwendet. 

### Templating
Die stärke von Bootique liegt bei der templating Funktionalität. Diese ermöglicht es jede erdenkliche Art von Kickstart-Files zu erstellen. Bootique verwendet im Hintergrund [Jinja](https://jinja.palletsprojects.com) als Templating-Engine.

Der Pfad zum Template unter `kickstart_template` wird relativ zum root-Verzeichnis der Konfiguration angegeben. Templates müssen daher nicht im `templates/` Verzeichnis liegen sondern können auch im selben Verzeichnis wie die der Maschinen Konfigurationen liegen.

Bootique sucht nur nach YAML-Dateien im root-Verzeichnis der Konfiguration. Bei Bedarf kann diese Funktionalität in Zukunft ergänzt werden, damit YAML-Dateien in Ordnern organisiert werden können. Zusammengefasst sieht die Verzeichnisstruktur des Konfiguration so aus:

```
.
├── machines.yaml
├── other_machines
│   └── test.yaml # <- Wird nicht berücksichtigt
└── templates
    ├── default.ks.j2
    └── store2.ks.j2
```

#### Vordefinierte Variablen im Template
Die Keys in der Konfiguration können im Template je nach belieben verwendet werden. Damit sind bei der Gestaltung der Konfiguration und der Templates nahezu keine Grenzen gesetzt. Folgende Variablen stehen im Template standardmäßig zu Verfügung und sollten nicht in der Konfiguration gesetzt werden:
- `hostname`: Beinhaltet den selben Wert wie `name` in der Konfiguration
- `os_repo_url`: Volle URL zum Repository. Setzt sich aus den Parametern `os`, `os_version` und `os_arch` in der Konfiguration zusammen.

#### Template Gestaltung
Grundsätzlich sollte aus dem gerenderten Template eine valide Kickstart-Datei herauskommen. Bootique checkt jedoch nicht, ob diese Kickstart Datei syntaktisch korrekt ist. Die Syntax kann mit dem Befehl `ksvalidate` überprüft werden. Die Semantik im ganzen kann jedoch nicht überprüft werden.

Im Endeffekt entscheidet man selbst, ob man für jede Maschine ein eigenes Template anlegt oder mit Jinja versucht es so generisch wie möglich zu halten. Es sollte ein guter Kompromiss gefunden werden, sodass die Wartbarkeit nicht darunter leidet.

Hier ist ein Beispiel für das Template `default.ks.j2`:

```jinja
# templates/default.ks.j2

lang en_US.UTF-8 --addsupport=de_AT.UTF-8,de_DE.UTF-8
keyboard --xlayouts='de (nodeadkeys)'
timezone Europe/Vienna --utc

# Network configuration
network  --bootproto=static --device=ens192 --gateway={{ ipv4_gw }} --ip={{ ipv4 }} --nameserver={{ ipv4_gw }} --netmask={{ ipv4_mask }} --ipv6=auto --activate --ipv4-dns-search=example.com --hostname={{ hostname }}

# Installaltion source
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

### Konfigurations Updates
Bootique parsed neue Konfiguration während der laufzeit. Ein Restart ist daher nicht erforderlich. Wird Bootique ohne gültigem Git-Repository als Umgebungsvariable `GIT_REPOSITORY` gestartet, dann wird die lokale Konfiguration unter `/data/config/` verwendet. Der Pfad kann mit der Umgebungsvariable `CONFIG_DIRECTORY` geändert werden.

Bei der lokalen Konfiguration setzt Bootique einen File-Event-Handler auf das Verzeichnis und lädt die Konfiguration nach jeder Änderung neu.<br>
Wenn Bootique die Konfiguration über ein Git-Repository bezieht, dann überprüft es alle 10 Sekunden, ob es einen neuen Commit am Repository gibt. Wenn das der Fall ist, cloned er sich das neue Repository und versucht die neue Konfiguration zu parsen.

Unabhängig davon welche Konfigurationsmethode verwendet wird: Wenn eine neue Konfiguration nicht eingelesen werden kann, wird die Alte weiter verwendet. Erst bei einer gültigen Konfiguration wird die Alte ersetzt.

## Starten
Wenn der `bootique.service` angelgt und die Konfiguration erstellt wurde, dann kann Bootique wie gewohnt mittels `systemctl start bootique.service` gestartet werden. Wenn alles Funktioniert, dann sollte folgendes im Log stehen:

```
[2025-05-31 13:25:44 +0000] [4] [INFO] Starting gunicorn 23.0.0
[2025-05-31 13:25:44 +0000] [4] [INFO] Listening at: http://0.0.0.0:443 (4)
[2025-05-31 13:25:44 +0000] [4] [INFO] Using worker: sync
[2025-05-31 13:25:44 +0000] [5] [INFO] Booting worker with pid: 5
{"time": "2025-05-31T13:25:44+0000", "level": "INFO", "message": "ConfigManagerThread started", "function": "run", "module": "ConfigManager"}
{"time": "2025-05-31T13:25:45+0000", "level": "INFO", "message": "New configuration from commit '7fbbcb616689e2067468b5c17bac585a831fafc0' with 3 machines successfully loaded", "function": "_run_git", "module": "ConfigManager"}
```

## Troubleshooting
Es gibt einige HTTP-Endpoints um die Konfiguration von Bootique auszulesen:
- `/admin/machines`: Liefert alle in Bootique konfigurierte Maschinen
- `/admin/machines/<machine_name>`: Liefert die Konfiguration für die im Pfad angegebene `machine_name`
- `/kickstart`: Gibt das gerenderte Kickstart-File zurück. Ohne Query-Parameter liefert es das Kickstart-File aus für die Source-IP des Requests. Um das Kickstart-File für eine spezifische Maschine zu bekommen muss `?ip=<requested_ip>` in der Anfrage angegeben werden. Auch `?mac=<requested_mac>` kann verwendet werden, wenn die deklarierte Maschine eine MAC-Adresse zugewiesen bekommen hat. Dies ist inbesondere erforderlich, wenn sich die anfordernde Maschine hinter einem NAT befindet.

✨ Happy Installing ✨