import os

AGENT_NAME = "do_it"
ORG_NAME = "Kni-org"

MAX_ITERATIONS = 40

WORKING_DIR = os.getcwd()

HOME_DIR = os.path.expanduser("~")
SESSION_DIR = os.path.join(HOME_DIR, ".do_it")
HISTORY_FILE = os.path.join(SESSION_DIR, "history.json")
BRIDGE_URL = "http://127.0.0.1:1514"

os.makedirs(SESSION_DIR, exist_ok=True)

