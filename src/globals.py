import os
# import pathlib

# import tftp
import ConfigManager

# !!! Do not modify above this line !!!
# ----- Begin Settings -----

# configured/supported RHEL distributions and their repos
DISTRIBUTION_REPOS = {
    "rocky": "http://repo{version}.parlament.gv.at/{version}/BaseOS/{architecture}/os",
    "rhel": "http://repo{version}.parlament.gv.at/RHEL/{version}/BaseOS"
}

# configuration for the TFTP server
TFTP_CONFIGURATION = {
    "address": os.getenv("TFTP_ADDRESS", "0.0.0.0"),
    "port": int(os.getenv("TFTP_PORT", "69")),
    "retries": int(os.getenv("TFTP_PACKET_RETRIES", "3")),
    "timeout": int(os.getenv("TFTP_PACKET_TIMEOUT", "5"))
}

# ----- End Settings -----
# !!! Do not modify below this line !!!

CONFIGMANAGER: ConfigManager.ConfigManagerThread
# TFTP_SERVER: tftp.TFTPServer
