#!/usr/bin/env python3
"""Daniel Bridge - OpenAI-compatible API proxy with jailbreak prompt injection.

Exposes a local API that proxies requests to OpenAI, injecting the "uncensored"
system prompt from Danielv2.1's config.json into every conversation.
"""

import http.server
import json
import os
import sys
import urllib.request
import urllib.error
import uuid

DANIEL_DIR = os.path.join(os.path.dirname(__file__), "..", "Danielv2.1")
CONFIG_PATH = os.path.join(DANIEL_DIR, "config.json")
HOST = os.environ.get("BRIDGE_HOST", "127.0.0.1")
PORT = int(os.environ.get("BRIDGE_PORT", "3456"))

def load_daniel_config():
    if not os.path.exists(CONFIG_PATH):
        print(f"[daniel-bridge] config.json not found at {CONFIG_PATH}")
        sys.exit(1)
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    return cfg.get("api_key"), cfg.get("system_message", ""), cfg.get("model", "gpt-3.5-turbo")

API_KEY, SYSTEM_PROMPT, DEFAULT_MODEL = load_daniel_config()
OPENAI_BASE = "https://api.openai.com/v1"


class DanielBridgeHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        print(f"[daniel-bridge] {args[0]} {args[1]} {args[2]}")

    def _send_json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self):
        if self.path == "/v1/models":
            self._handle_list_models()
        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        if self.path == "/v1/chat/completions":
            self._handle_chat_completions()
        else:
            self._send_json({"error": "not found"}, 404)

    def _handle_list_models(self):
        models = {
            "object": "list",
            "data": [
                {
                    "id": DEFAULT_MODEL,
                    "object": "model",
                    "created": 1700000000,
                    "owned_by": "daniel-bridge",
                }
            ],
        }
        self._send_json(models)

    def _handle_chat_completions(self):
        try:
            body = self._read_body()
        except json.JSONDecodeError:
            self._send_json({"error": "invalid JSON"}, 400)
            return

        messages = body.get("messages", [])
        model = body.get("model", DEFAULT_MODEL)
        stream = body.get("stream", False)
        temperature = body.get("temperature", 0.7)
        max_tokens = body.get("max_tokens", 4096)
        top_p = body.get("top_p", 1.0)

        if SYSTEM_PROMPT:
            has_system = any(m.get("role") == "system" for m in messages)
            if not has_system:
                messages.insert(0, {"role": "system", "content": SYSTEM_PROMPT})

        openai_payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": top_p,
            "stream": stream,
        }

        req_body = json.dumps(openai_payload).encode()
        req = urllib.request.Request(
            f"{OPENAI_BASE}/chat/completions",
            data=req_body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {API_KEY}",
            },
            method="POST",
        )

        if stream:
            self._proxy_stream(req)
        else:
            self._proxy_non_stream(req)

    def _proxy_non_stream(self, req):
        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read())
                data["model"] = DEFAULT_MODEL
                self._send_json(data, resp.status)
        except urllib.error.HTTPError as e:
            error_body = e.read().decode()
            self._send_json(json.loads(error_body) if error_body else {"error": str(e)}, e.code)
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _proxy_stream(self, req):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        try:
            with urllib.request.urlopen(req) as upstream:
                while True:
                    line = upstream.readline()
                    if not line:
                        break
                    decoded = line.decode("utf-8", errors="replace")
                    if decoded.startswith("data: ") and "[DONE]" not in decoded:
                        try:
                            chunk = json.loads(decoded[6:])
                            chunk["model"] = DEFAULT_MODEL
                            self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
                            self.wfile.flush()
                        except json.JSONDecodeError:
                            self.wfile.write(decoded.encode())
                            self.wfile.flush()
                    else:
                        self.wfile.write(decoded.encode())
                        self.wfile.flush()
        except Exception as e:
            self.wfile.write(f"data: {json.dumps({'error': str(e)})}\n\n".encode())
            self.wfile.flush()
        finally:
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()


def main():
    server = http.server.HTTPServer((HOST, PORT), DanielBridgeHandler)
    print(f"[daniel-bridge] Running on http://{HOST}:{PORT}")
    print(f"[daniel-bridge] Using OpenAI model: {DEFAULT_MODEL}")
    print(f"[daniel-bridge] System prompt: {len(SYSTEM_PROMPT)} chars")
    print(f"[daniel-bridge] Endpoints:")
    print(f"  GET  http://{HOST}:{PORT}/v1/models")
    print(f"  POST http://{HOST}:{PORT}/v1/chat/completions")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[daniel-bridge] Light's Out It's Bed Time Kiddo")
        server.server_close()


if __name__ == "__main__":
    main()
