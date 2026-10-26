#!/usr/bin/env python3
"""
COSMIC-NEXUS Local Server
A lightweight, zero-dependency Python server to serve the COSMIC-NEXUS web app.

Usage:
    python server.py [port]
"""

import os
import sys
import webbrowser
import http.server
import socketserver

DEFAULT_PORT = 8000

class CosmicRequestHandler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {
        '': 'application/octet-stream',
        '.html': 'text/html; charset=utf-8',
        '.css': 'text/css; charset=utf-8',
        '.js': 'application/javascript; charset=utf-8',
        '.mjs': 'application/javascript; charset=utf-8',
        '.json': 'application/json; charset=utf-8',
        '.csv': 'text/csv; charset=utf-8',
        '.svg': 'image/svg+xml',
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.ico': 'image/x-icon',
        '.woff': 'font/woff',
        '.woff2': 'font/woff2',
        '.ttf': 'font/ttf',
    }

    def end_headers(self):
        # Prevent aggressive caching during prototyping and testing
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        super().end_headers()

    def log_message(self, format, *args):
        # Clean terminal output format
        sys.stdout.write(f"[{self.log_date_time_string()}] {args[0]} {args[1]}\n")
        sys.stdout.flush()

def find_available_port(start_port):
    import socket
    port = start_port
    while port < 65535:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', port)) != 0:
                return port
            port += 1
    return start_port

def run_server(port=DEFAULT_PORT, open_browser=True):
    # Ensure current directory is the directory of server.py
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    port = find_available_port(port)
    url = f"http://127.0.0.1:{port}/"

    print("=" * 64)
    print(" COSMIC-NEXUS · Astronaut Health & Cabin Simulation")
    print(" Zero-dependency standalone HTML5 / CSS3 / ES-Module App")
    print("=" * 64)
    print(f" Server running at: {url}")
    print(f" Directory:        {os.getcwd()}")
    print(" Press Ctrl+C to stop the server.\n")

    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    with socketserver.TCPServer(("", port), CosmicRequestHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server. Goodbye!")

if __name__ == '__main__':
    port = DEFAULT_PORT
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print(f"Invalid port: {sys.argv[1]}, using default {DEFAULT_PORT}")
    run_server(port)
