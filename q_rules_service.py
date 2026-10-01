"""Small HTTP service: GitHub credentials stay on the server, never in EXEs.

Run with PYTHONPATH=src python services/q_rules_service.py behind HTTPS.
Only the fixed q_rules.json file in the release repository can be written.
"""

from __future__ import annotations

import base64
import hmac
import json
import os
import threading
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from manifest_editor.q_rules_sync import RuleConflict, merge_rules, rule_objects, validate_rules

CONTENT_URL = "https://api.github.com/repos/blkvl01/manifest-szerkeszto-releases/contents/q_rules.json"
MAX_BODY = 1024 * 1024


class GitHubStore:
    def __init__(self, token: str) -> None:
        self.token = token
        self.lock = threading.Lock()

    def request(self, method: str, payload: dict | None = None) -> dict:
        request = urllib.request.Request(
            CONTENT_URL + ("?ref=main" if method == "GET" else ""),
            data=None if payload is None else json.dumps(payload).encode("utf-8"),
            method=method,
            headers={
                "Authorization": "Bearer " + self.token,
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json",
                "User-Agent": "ManifestSzerkeszto-Q-rules",
                "X-GitHub-Api-Version": "2026-03-10",
            },
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.load(response)

    def save(self, body: dict) -> dict:
        base = validate_rules(body.get("base"), allow_empty=True)
        desired = validate_rules(body.get("rules"))
        editor = body.get("editor", "Munkatárs")
        if not isinstance(editor, str) or not editor.strip() or len(editor) > 80 or any(ord(c) < 32 for c in editor):
            raise ValueError("Érvénytelen szerkesztőnév.")
        # Serialize on this instance; the GitHub SHA also guards other instances.
        with self.lock:
            for attempt in range(3):
                entry = self.request("GET")
                current_payload = json.loads(base64.b64decode(entry["content"]).decode("utf-8-sig"))
                if current_payload.get("schema_version") != 1 or not isinstance(current_payload.get("revision"), str):
                    raise ValueError("A közös fájl formátuma nem támogatott.")
                current = validate_rules(current_payload.get("rules"))
                try:
                    merged = merge_rules(base, desired, current)
                except RuleConflict as exc:
                    exc.current_payload = current_payload
                    raise
                if merged == current:
                    return current_payload
                revision = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:12]
                payload = {"schema_version": 1, "revision": revision, "rules": rule_objects(merged)}
                encoded = base64.b64encode((json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")).decode("ascii")
                try:
                    self.request("PUT", {
                        "message": f"Q szabályok módosítása – {editor.strip()} [{revision}]",
                        "content": encoded, "sha": entry["sha"], "branch": "main",
                    })
                    return payload
                except urllib.error.HTTPError as exc:
                    if exc.code != 409 or attempt == 2:
                        raise
        raise RuntimeError("A közös mentés ismételt ütközés miatt nem sikerült.")


def make_handler(store: GitHubStore, access_key: str):
    configured = len(access_key) >= 32 and bool(getattr(store, "token", True))
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            # Never put client credentials or rule contents into access logs.
            pass

        def respond(self, status: int, body: dict) -> None:
            encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self):
            if self.path == "/health":
                self.respond(200, {"status": "ok", "configured": configured})
            else:
                self.respond(404, {"error": "Nem található."})

        def do_POST(self):
            self.connection.settimeout(15)
            if self.path != "/q-rules":
                self.respond(404, {"error": "Nem található."})
                return
            if not configured:
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if 0 < length <= MAX_BODY:
                        self.rfile.read(length)
                except (ValueError, OSError):
                    pass
                self.respond(503, {"error": "A közös mentés még nincs bekapcsolva."})
                return
            supplied = self.headers.get("Authorization", "")
            if not hmac.compare_digest(supplied.encode(), ("Bearer " + access_key).encode()):
                # Drain small requests before closing, avoiding a TCP reset on Windows.
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if 0 < length <= MAX_BODY:
                        self.rfile.read(length)
                except (ValueError, OSError):
                    pass
                self.respond(401, {"error": "A közös mentési jogosultság hiányzik vagy érvénytelen."})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > MAX_BODY:
                    self.respond(413, {"error": "A kérés mérete érvénytelen."})
                    return
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError("Érvénytelen kérés.")
                self.respond(200, store.save(body))
            except RuleConflict as exc:
                self.respond(409, {"error": str(exc), "conflicts": exc.patterns, "current": exc.current_payload})
            except (ValueError, TypeError, KeyError):
                self.respond(400, {"error": "Érvénytelen szabálykészlet vagy közös fájl."})
            except (OSError, urllib.error.URLError):
                self.respond(503, {"error": "A közös mentés most nem érhető el. A módosítás helyben megmarad."})
    return Handler


if __name__ == "__main__":
    token = os.environ.get("Q_RULES_GITHUB_TOKEN", "")
    key = os.environ.get("Q_RULES_ACCESS_KEY", "")
    if not token or len(key) < 32:
        print("A szolgáltatás elindult; a közös mentés a jogosultság beállításáig le van tiltva.", flush=True)
    server = ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "8080"))), make_handler(GitHubStore(token), key))
    server.daemon_threads = True
    server.serve_forever()
