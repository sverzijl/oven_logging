#!/usr/bin/env python
"""Tiny CORS-enabled static server for the browser file-upload workaround.

The Streamlit app does nothing until a CSV is uploaded via the sidebar, but the
agent's browser ``file_upload`` tool refuses host filesystem paths. Workaround:
serve the repo's CSVs from here, then have the Streamlit page ``fetch`` one and
inject it into the uploader's hidden ``<input type=file>`` (see SKILL.md ->
"Run (real browser UI)"). The CORS header is required because the page
(localhost:8765) and this server (localhost:8799) are different origins.

    python .claude/skills/run-oven-logging/serve_csv.py [PORT]   # default 8799

Serves the repo root (where the ProbeData_*.csv live), regardless of CWD.
"""
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


class CORSHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(REPO), **kwargs)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def log_message(self, *args):  # quiet
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8799
    print(f"Serving {REPO} at http://127.0.0.1:{port} (Access-Control-Allow-Origin: *)")
    HTTPServer(("127.0.0.1", port), CORSHandler).serve_forever()
