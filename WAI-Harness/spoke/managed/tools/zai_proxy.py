#!/usr/bin/env python3
"""
Minimal OpenAI-to-Anthropic streaming proxy for gitnexus wiki.

gitnexus wiki only speaks OpenAI SSE format. Z.ai exposes Anthropic format.
This proxy bridges them: receives OpenAI /v1/chat/completions, forwards to
Z.ai Anthropic endpoint, converts SSE back to OpenAI format.

Usage (run in background during wiki generation):
    python3 tools/zai_proxy.py &
    OPENAI_API_KEY=dummy gitnexus wiki --base-url http://localhost:18080/v1 --model claude-sonnet-4-6
    kill %1
"""

import http.server
import json
import urllib.request
import urllib.error
import sys

ZAI_URL = "https://api.z.ai/api/anthropic/v1/messages"
KEY_FILE = "/home/mario/.zai_api_key"
PORT = 18080


def _key():
    with open(KEY_FILE) as f:
        return f.read().strip()


def _to_anthropic(body):
    messages, system = [], None
    for m in body.get("messages", []):
        if m["role"] == "system":
            system = m["content"]
        else:
            messages.append(m)
    out = {
        "model": body.get("model", "claude-sonnet-4-6"),
        "messages": messages,
        "max_tokens": body.get("max_tokens", 4096),
        "stream": True,
    }
    if system:
        out["system"] = system
    return out


def _convert_line(line):
    """Anthropic SSE line → OpenAI SSE chunk string, or None to skip."""
    if not line.startswith("data:"):
        return None
    raw = line[5:].strip()
    if not raw:
        return None
    try:
        d = json.loads(raw)
    except Exception:
        return None
    t = d.get("type", "")
    if t == "content_block_delta":
        text = d.get("delta", {}).get("text", "")
        return "data: " + json.dumps({"choices": [{"delta": {"content": text}, "finish_reason": None}]}) + "\n\n"
    if t == "message_stop":
        return (
            "data: " + json.dumps({"choices": [{"delta": {}, "finish_reason": "stop"}]}) + "\n\n"
            + "data: [DONE]\n\n"
        )
    return None


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_POST(self):
        if "/chat/completions" not in self.path:
            self.send_response(404)
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        anth = _to_anthropic(body)

        req = urllib.request.Request(
            ZAI_URL,
            data=json.dumps(anth).encode(),
            headers={
                "Authorization": f"Bearer {_key()}",
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            resp = urllib.request.urlopen(req, timeout=120)
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(e.read())
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        for raw in resp:
            chunk = _convert_line(raw.decode("utf-8").rstrip("\n"))
            if chunk:
                try:
                    self.wfile.write(chunk.encode())
                    self.wfile.flush()
                except BrokenPipeError:
                    break
        resp.close()


if __name__ == "__main__":
    server = http.server.HTTPServer(("127.0.0.1", PORT), _Handler)
    print(f"zai_proxy ready on http://127.0.0.1:{PORT}/v1", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("proxy stopped")
