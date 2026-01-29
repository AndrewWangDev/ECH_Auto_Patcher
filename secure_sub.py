#!/usr/bin/env python3
import dns.resolver
import base64
import zlib
import time
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

# Server settings
SERVER_IP = '0.0.0.0'
SERVER_PORT = 25500
SECRET_PATH = "/sub/replace_with_your_uuid"  # Replace with your own path

# Target domain for ECH fetching
# Replace test.example.com to your own (sub)domain
REAL_DOMAIN = "test.example.com"

# Exclave export string containing the 'a' placeholder
# Replace the string below with your own exported URI
RAW_BACKUP_URI = "exclave://vmess?YOUR_EXPORT_DATA_HERE"

# Pattern to locate the placeholder (40 'a's)
SEARCH_PATTERN = b"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

# Global buffer for the subscription content
CURRENT_SUB_CONTENT = b""

def get_ech_config(domain):
    """Fetch ECH config from Cloudflare DNS."""
    print(f"[DNS] Querying {domain}...")
    try:
        resolver = dns.resolver.Resolver()
        resolver.nameservers = ['1.1.1.1', '1.0.0.1']
        answers = resolver.resolve(domain, 'HTTPS')
        for rdata in answers:
            if 5 in rdata.params:
                ech_obj = rdata.params[5]
                ech_bytes = None
                
                if hasattr(ech_obj, 'ech'):
                    ech_bytes = ech_obj.ech
                elif hasattr(ech_obj, 'data'):
                    ech_bytes = ech_obj.data
                else:
                    try: ech_bytes = bytes(ech_obj)
                    except: pass
                
                if ech_bytes:
                    return base64.b64encode(ech_bytes).decode('utf-8')
    except Exception as e:
        print(f"[DNS] Error: {e}")
    return None

def patch_protobuf(data, new_val_str):
    """Replace placeholder in protobuf binary with fixed length."""
    new_bytes = new_val_str.encode('utf-8')
    
    start_idx = data.find(SEARCH_PATTERN)
    if start_idx == -1:
        print("[Error] Placeholder not found.")
        return None
    
    # Locate placeholder boundaries
    end_idx = start_idx
    while end_idx < len(data) and data[end_idx] == 97:  # 97 is 'a'
        end_idx += 1
    
    real_start = start_idx
    while real_start > 0 and data[real_start - 1] == 97:
        real_start -= 1
        
    capacity = end_idx - real_start
    print(f"[Debug] Placeholder capacity: {capacity} bytes")
    
    if len(new_bytes) > capacity:
        print(f"[Error] New value exceeds capacity.")
        return None
        
    # Pad with spaces
    padding = b' ' * (capacity - len(new_bytes))
    return data[:real_start] + new_bytes + padding + data[end_idx:]

def generate_sub():
    """Main workflow: Fetch -> Patch -> Pack."""
    global CURRENT_SUB_CONTENT

    ech = get_ech_config(REAL_DOMAIN)
    if not ech:
        return

    try:
        # Unpack
        b64_str = RAW_BACKUP_URI.replace("exclave://vmess?", "").strip()
        padding = len(b64_str) % 4
        if padding:
            b64_str += "=" * (4 - padding)
        
        raw_proto = zlib.decompress(base64.urlsafe_b64decode(b64_str))
        
        # Patch
        patched_proto = patch_protobuf(raw_proto, ech)
        if not patched_proto:
            return

        # Repack
        compressed = zlib.compress(patched_proto)
        new_b64 = base64.urlsafe_b64encode(compressed).decode('utf-8').rstrip("=")
        final_uri = f"exclave://vmess?{new_b64}"
        
        # Encode for subscription
        CURRENT_SUB_CONTENT = base64.b64encode(final_uri.encode('utf-8'))
        print(f"[Success] Updated ECH: {ech[:8]}...")

    except Exception as e:
        print(f"[Error] Update failed: {e}")

def loop():
    while True:
        generate_sub()
        time.sleep(3000)  # 50 minutes

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == SECRET_PATH:
            self.send_response(200)
            self.send_header('Content-type', 'text/plain; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(CURRENT_SUB_CONTENT)
        else:
            self.send_response(404)
            self.end_headers()

if __name__ == "__main__":
    generate_sub()
    t = threading.Thread(target=loop, daemon=True)
    t.start()
    
    server = HTTPServer((SERVER_IP, SERVER_PORT), Handler)
    print(f"Serving at http://{SERVER_IP}:{SERVER_PORT}{SECRET_PATH}")
    server.serve_forever()