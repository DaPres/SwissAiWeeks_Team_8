"""Serve Intake's frontend and API using only the Python standard library."""

import argparse
import json
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/api/health":
            body = json.dumps({"status": "ok", "app": "intake"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path.startswith("/api/"):
            self.send_error(404, "Unknown API endpoint")
        else:
            super().do_GET()


def main():
    parser = argparse.ArgumentParser(description="Run Intake locally")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    public = Path(__file__).resolve().parent / "public"
    handler = partial(Handler, directory=str(public))
    with ThreadingHTTPServer(("127.0.0.1", args.port), handler) as server:
        print(f"Intake is running at http://127.0.0.1:{args.port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
