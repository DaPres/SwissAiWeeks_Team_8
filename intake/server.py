"""Serve Intake's frontend and API using only the Python standard library."""

import argparse
import json
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from incidents import create_ready_incident
from quality import QualityError, evaluate_description
from suggestions import suggest_description
from triagemate_demo import preview_incident


class Handler(SimpleHTTPRequestHandler):
    def send_json(self, status, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        path = urlsplit(self.path).path
        if path not in ("/api/incidents", "/api/description-quality", "/api/description-suggestion", "/api/triagemate-demo"):
            self.send_json(404, {"error": "Unknown API endpoint."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 100000:
                self.send_json(413, {"error": "Request body must be between 1 and 100000 bytes."})
                return
            data = json.loads(self.rfile.read(length))
            if path == "/api/description-quality":
                result = evaluate_description(data)
            elif path == "/api/description-suggestion":
                result = suggest_description(data)
            elif path == "/api/triagemate-demo":
                result = preview_incident(data)
            else:
                result = create_ready_incident(data)
        except QualityError as error:
            self.send_json(error.status, {"error": str(error)})
            return
        except (ValueError, UnicodeDecodeError) as error:
            self.send_json(400, {"error": str(error)})
            return
        except ImportError:
            self.send_json(503, {"error": "TriageMate dependencies are unavailable. Install main2/requirements.txt and run Intake with that Python environment."})
            return
        except Exception:
            self.log_error("Request failed for %s", path)
            self.send_json(500, {"error": "Could not complete the request. Please try again."})
            return
        self.send_json(201 if path == "/api/incidents" else 200, result)

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
    frontend = Path(__file__).resolve().parent / "dist"
    if not (frontend / "index.html").exists():
        print("Frontend build missing. Run npm ci && npm run build, or use npm run dev.", flush=True)
    handler = partial(Handler, directory=str(frontend))
    with ThreadingHTTPServer(("127.0.0.1", args.port), handler) as server:
        print(f"Intake is running at http://127.0.0.1:{args.port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
