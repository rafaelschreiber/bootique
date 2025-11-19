import os
import ConfigManager

# Build up distribution repos out of environment variables starting with 'REPO_'
DISTRIBUTION_REPOS = {}
for repo_var in filter(lambda e: e[:5] == "REPO_", os.environ.keys()):
    DISTRIBUTION_REPOS[repo_var[5:].lower()] = os.getenv(repo_var)

CONFIGMANAGER: ConfigManager.ConfigManagerThread
