"""Exercise the probe against an isolated HTTP fixture, without a game server."""

import copy
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import unittest
from unittest.mock import patch

from probe_mrad import MAX_RESPONSE_BYTES, ProbeError, probe, validate_url


HEALTH = {"database": "C:/synthetic/save.sqlite", "processId": 42, "readApiVersion": 1,
          "authentication": "loopback", "onlineMail": True, "adminManagement": True,
          "clientFingerprint": "fixture"}
CAPABILITIES = {"items": [{"key": "account.list", "implemented": True}],
                **dict.fromkeys(("console", "mail", "content", "strings", "index", "icons", "administration"), True)}


@contextmanager
def server(respond):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append((self.command, self.path, self.headers.get("X-GM-Process-Id")))
            status, body, headers = respond(self.path, len(requests))
            body = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", headers.pop("Content-Type", "application/json"))
            self.send_header("Content-Length", str(len(body)))
            for name, value in headers.items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=http.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{http.server_port}", requests
    finally:
        http.shutdown()
        http.server_close()
        thread.join(timeout=2)


def normal(path, count):
    return 200, HEALTH if path.endswith("/health") else CAPABILITIES, {}


class ProbeTests(unittest.TestCase):
    def test_only_gets_pinned_to_process_and_ignores_proxy(self):
        with server(normal) as (url, requests), patch.dict("os.environ", {
            "http_proxy": "http://127.0.0.1:1", "HTTP_PROXY": "http://127.0.0.1:1", "no_proxy": "", "NO_PROXY": ""
        }):
            result = probe(url)
        self.assertEqual(result["status"], "compatible")
        self.assertFalse(result["writeEnabled"])
        self.assertNotIn("database", result)
        self.assertEqual(requests, [("GET", "/gm/tool/health", None),
                                    ("GET", "/gm/capabilities", "42"),
                                    ("GET", "/gm/tool/health", "42")])

    def test_rejects_non_loopback_or_ambiguous_urls(self):
        for url in ("http://example.com:7000", "http://localhost:7000", "https://127.0.0.1",
                    "http://127.0.0.1:0", "http://127.0.0.1:65536", "http://user:pass@127.0.0.1",
                    "http://127.0.0.1/gm", "http://127.0.0.1?", "http://127.0.0.1#",
                    "http://127.0.0.1\n", "http://[::1%25lo]:7000", "http://192.168.1.1:7000"):
            with self.subTest(url=url), self.assertRaises(ProbeError):
                validate_url(url)
        self.assertEqual(validate_url("http://[::1]:7000/"), "http://[::1]:7000")

    def test_redirects_are_not_followed(self):
        with server(lambda p, n: (302, {}, {"Location": "/redirected"})) as (url, requests):
            with self.assertRaisesRegex(ProbeError, "HTTP 302"):
                probe(url)
        self.assertEqual(len(requests), 1)

    def test_rejects_invalid_health_contract(self):
        for key, value in (("readApiVersion", None), ("readApiVersion", 2), ("readApiVersion", True),
                           ("authentication", "none"), ("processId", 0), ("database", ""),
                           ("clientFingerprint", {}), ("onlineMail", 1)):
            health = {**HEALTH, key: value}
            with self.subTest(key=key, value=value), server(lambda p, n: (200, health, {})) as (url, requests):
                with self.assertRaises(ProbeError):
                    probe(url)
                self.assertEqual(len(requests), 1)

    def test_rejects_identity_change(self):
        for key, value in (("processId", 43), ("database", "other.sqlite"), ("clientFingerprint", "other")):
            def respond(path, count):
                return (200, {**HEALTH, key: value}, {}) if count == 3 else normal(path, count)
            with self.subTest(key=key), server(respond) as (url, _):
                with self.assertRaisesRegex(ProbeError, "identity changed"):
                    probe(url)

    def test_rejects_http_errors_and_invalid_responses(self):
        cases = [(403, {}, {}), (409, {}, {}), (503, {}, {}),
                 (200, b"<html>wrong port</html>", {"Content-Type": "text/html"}),
                 (200, b"{", {}), (200, b'{"number":NaN}', {}),
                 (200, [], {}), (200, b" " * (MAX_RESPONSE_BYTES + 1), {})]
        for status, body, headers in cases:
            with self.subTest(status=status, size=len(body)), server(
                lambda p, n: (status, body, headers.copy())
            ) as (url, _):
                with self.assertRaises(ProbeError):
                    probe(url)

    def test_rejects_invalid_capabilities(self):
        for key, value in (("items", {}), ("items", [{}]), ("items", [{"key": "x", "implemented": "true"}]),
                           ("console", None)):
            caps = {**CAPABILITIES, key: value}
            with self.subTest(key=key), server(lambda p, n: (200, HEALTH if n == 1 else caps, {})) as (url, _):
                with self.assertRaises(ProbeError):
                    probe(url)

    def test_unready_resources_are_preserved(self):
        caps = copy.deepcopy(CAPABILITIES)
        caps["icons"] = False
        with server(lambda p, n: (200, caps, {}) if n == 2 else normal(p, n)) as (url, _):
            result = probe(url)
        self.assertFalse(result["resources"]["icons"])

    def test_timeout_validation(self):
        for timeout in (0, -1, 31, float("nan"), float("inf")):
            with self.subTest(timeout=timeout), self.assertRaises(ProbeError):
                probe(timeout=timeout)


if __name__ == "__main__":
    unittest.main()
