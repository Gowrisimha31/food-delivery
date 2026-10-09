# deploy.py
# Announces new versions of the app in the logs.
# Real companies log every deployment, because "what changed recently?"
# is the first question asked when something breaks.

from logger import log

CURRENT_VERSION = "1.0.0"


def announce_deploy(version, change):
    global CURRENT_VERSION
    CURRENT_VERSION = version
    log.info("Deployment completed", extra={"version": version, "change": change})


def announce_rollback(version):
    global CURRENT_VERSION
    CURRENT_VERSION = version
    log.info("Rollback completed", extra={"version": version})