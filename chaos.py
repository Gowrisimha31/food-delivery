# chaos.py
# The "break switches". Each one makes the app fail in a realistic way.
# Turn them on and off from /docs, under "Chaos".
#
# IMPORTANT: switching a fault on or off is recorded ONLY in logs/chaos.log,
# never in logs/app.log. app.log is what the AI reads, and it must not
# see the answer. chaos.log is our answer key for testing the AI later.

import logging
from fastapi import APIRouter, HTTPException
from logger import JSONFormatter
from deploy import announce_deploy, announce_rollback

# Each switch, whether it's on, and what it imitates in real life
FAULTS = {
    "payment_gateway_down": {"on": False, "imitates": "The payment company's servers are down"},
    "slow_database": {"on": False, "imitates": "The database is overloaded and slow"},
    "db_connections_exhausted": {"on": False, "imitates": "The app has run out of database connections"},
    "bad_deploy": {"on": False, "imitates": "A developer released buggy code"},
}

# A separate log file that records when we flip switches (the answer key)
chaos_log = logging.getLogger("chaos")
chaos_log.setLevel(logging.INFO)
chaos_log.propagate = False
_handler = logging.FileHandler("logs/chaos.log")
_handler.setFormatter(JSONFormatter())
chaos_log.addHandler(_handler)


def is_on(name):
    return FAULTS[name]["on"]


router = APIRouter(prefix="/chaos", tags=["Chaos (break switches)"])


@router.get("")
def list_faults():
    return FAULTS


@router.post("/{name}/on")
def turn_on(name: str):
    if name not in FAULTS:
        raise HTTPException(status_code=404, detail="No such fault")
    FAULTS[name]["on"] = True
    chaos_log.info("Fault turned ON", extra={"fault": name})

    # A real deployment is announced in the logs, so this one is too.
    if name == "bad_deploy":
        announce_deploy("1.1.0", "Added restaurant discounts")
    return {"fault": name, "on": True}


@router.post("/{name}/off")
def turn_off(name: str):
    if name not in FAULTS:
        raise HTTPException(status_code=404, detail="No such fault")
    FAULTS[name]["on"] = False
    chaos_log.info("Fault turned OFF", extra={"fault": name})

    if name == "bad_deploy":
        announce_rollback("1.0.0")
    return {"fault": name, "on": False}


@router.post("/reset")
def reset_all():
    for name in FAULTS:
        if FAULTS[name]["on"]:
            turn_off(name)
    return FAULTS