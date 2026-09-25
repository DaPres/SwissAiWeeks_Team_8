"""Serve Intake's frontend and API using only the Python standard library."""

import argparse
import json
import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from incidents import (IncidentError, create_ready_incident, decide_incident, list_incidents,
                       new_incident_id, save_processed_incident, validate_handoff)
from quality import QualityError, complete_evaluation, evaluate_description
from suggestions import suggest_description
from engine_client import EngineError, complete_draft_fields, preview_incident


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
        decision_id = (path.removeprefix('/api/incidents/').removesuffix('/decision').strip('/')
                       if path.startswith('/api/incidents/') and path.endswith('/decision') else None)
        if path not in ("/api/incidents", "/api/incident-process", "/api/description-quality", "/api/incident-suggestions",
                        "/api/description-suggestion", "/api/triagemate-demo") and decision_id is None:
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
            elif path == '/api/incident-suggestions':
                result = complete_evaluation(data, complete_fields=complete_draft_fields)
            elif path == "/api/description-suggestion":
                result = suggest_description(data)
            elif path == "/api/triagemate-demo":
                result = preview_incident(data)
            elif path == "/api/incident-process":
                draft = validate_handoff(data)
                identifier = new_incident_id()
                enriched = preview_incident({'description': draft['description'], 'details': draft['fields']}, identifier)
                result = save_processed_incident(draft, enriched, identifier)
            elif decision_id is not None:
                if not isinstance(data, dict):
                    raise ValueError('A decision is required.')
                result = decide_incident(decision_id, data.get('decision'), data.get('account'))
            else:
                result = create_ready_incident(data)
        except QualityError as error:
            self.send_json(error.status, {"error": str(error), **({'debug': error.debug} if error.debug else {})})
            return
        except (IncidentError, EngineError) as error:
            self.send_json(error.status, {"error": str(error)})
            return
        except (ValueError, UnicodeDecodeError) as error:
            self.send_json(400, {"error": str(error)})
            return
        except (ImportError, FileNotFoundError):
            self.send_json(503, {"error": "Intake dependencies are unavailable. Run uv sync in intake and start Aspire."})
            return
        except Exception:
            self.log_error("Request failed for %s", path)
            self.send_json(500, {"error": "Could not complete the request. Please try again."})
            return
        self.send_json(201 if path in ("/api/incidents", "/api/incident-process") else 200, result)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/api/health":
            body = json.dumps({"status": "ok", "app": "intake"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == '/api/incidents':
            try:
                account = parse_qs(urlsplit(self.path).query).get('account', ['client'])[0]
                self.send_json(200, {'incidents': list_incidents(account)})
            except ValueError as error:
                self.send_json(400, {'error': str(error)})
        elif path.startswith("/api/"):
            self.send_error(404, "Unknown API endpoint")
        else:
            super().do_GET()


def main():
    parser = argparse.ArgumentParser(description="Run Intake locally")
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8081")))
    args = parser.parse_args()
    frontend = Path(__file__).resolve().parent / "dist"
    if not (frontend / "index.html").exists():
        print("Frontend build missing. Run npm ci && npm run build, or use npm run dev.", flush=True)
    handler = partial(Handler, directory=str(frontend))
    with ThreadingHTTPServer((args.host, args.port), handler) as server:
        print(f"Intake is running at http://{args.host}:{args.port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
