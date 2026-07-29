#!/usr/bin/env python3
"""Local dev server with caching fully disabled.

Plain `python3 -m http.server` sends no Cache-Control header, so browsers can hold onto old
JS module files across reloads during active iteration -- which is exactly what happened here
(a corrected file was live on disk and confirmed via curl, but the browser still rendered the
previous version). This wrapper adds `Cache-Control: no-store` to every response so a normal
reload always reflects what's on disk.
"""
import http.server
import sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4173


class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Pragma", "no-cache")
        super().end_headers()


if __name__ == "__main__":
    http.server.test(HandlerClass=NoCacheHandler, port=PORT)
