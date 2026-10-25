"""Read-only Mrad Max handshake; uses Python 3.11+ and no third-party packages."""

import argparse
import http.client
import ipaddress
import json
import math
import re
import urllib.error
import urllib.parse
import urllib.request


DEFAULT_URL = "http://127.0.0.1:7000"
MAX_RESPONSE_BYTES = 1024 * 1024
PATHS = frozenset({"/gm/tool/health", "/gm/capabilities"})


class ProbeError(ValueError):
    """The server could not be verified for this read API."""
    def __init__(self, message, status=502):
        super().__init__(message)
        self.status = status


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def make_opener():
    # This protocol accepts HTTP loopback only. Construct only its HTTP handlers,
    # without initializing an unused system TLS context in the frozen runtime.
    opener = urllib.request.OpenerDirector()
    for handler in (urllib.request.ProxyHandler({}), urllib.request.HTTPHandler(),
                    urllib.request.HTTPDefaultErrorHandler(), NoRedirect(),
                    urllib.request.HTTPErrorProcessor(), urllib.request.UnknownHandler()):
        opener.add_handler(handler)
    return opener


def validate_url(value):
    """Require a literal loopback IP: no DNS, credentials or proxy endpoint."""
    try:
        if not value or any(c.isspace() or ord(c) < 32 for c in value):
            raise ValueError()
        url = urllib.parse.urlsplit(value)
        if (url.scheme != "http" or url.username is not None
                or url.password is not None or url.path not in ("", "/")
                or "?" in value or "#" in value or "%" in value):
            raise ValueError()
        address = ipaddress.ip_address(url.hostname or "")
        if not address.is_loopback:
            raise ValueError()
        port = url.port if url.port is not None else 80
        if not 1 <= port <= 65535:
            raise ValueError()
        host = f"[{address}]" if address.version == 6 else str(address)
        return f"http://{host}:{port}"
    except ValueError:
        raise ProbeError("Use an HTTP loopback IP URL, for example " + DEFAULT_URL) from None


def reject_constant(value):
    raise ValueError("Non-finite JSON number")


def get_json(opener, base_url, path, timeout, process_id=None):
    if path not in PATHS and not re.fullmatch(
        r'/gm/(?:accounts|characters(?:\?accountId=[1-9][0-9]{0,18})?|tool/characters/[1-9][0-9]{0,18}/progress\?accountId=[1-9][0-9]{0,18})', path
    ):
        raise ProbeError("Endpoint is outside the read-only probe allowlist")
    headers = {"Accept": "application/json"}
    if process_id is not None:
        headers["X-GM-Process-Id"] = str(process_id)
    request = urllib.request.Request(base_url + path, headers=headers, method="GET")
    try:
        with opener.open(request, timeout=timeout) as response:
            if response.status != 200:
                raise ProbeError(f"{path}: unexpected HTTP {response.status}")
            if response.headers.get_content_type() != "application/json":
                raise ProbeError(f"{path}: expected application/json")
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise ProbeError(f"{path}: response exceeds 1 MiB")
    except urllib.error.HTTPError as exc:
        status = exc.code
        exc.close()
        explanations = {403: "loopback access rejected", 409: "server identity changed",
                        503: "GM resources are not ready"}
        raise ProbeError(f"{path}: HTTP {status} ({explanations.get(status, 'request rejected')})", status) from None
    except (OSError, urllib.error.URLError, http.client.HTTPException) as exc:
        raise ProbeError(f"{path}: connection failed ({type(exc).__name__})", 503) from None
    try:
        data = json.loads(raw, parse_constant=reject_constant)
    except (ValueError, UnicodeError):
        raise ProbeError(f"{path}: invalid JSON") from None
    if not isinstance(data, (dict, list)):
        raise ProbeError(f"{path}: expected a JSON object or array")
    return data


def health_identity(health):
    if not isinstance(health, dict):
        raise ProbeError("Expected a health object")
    if type(health.get("readApiVersion")) is not int or health["readApiVersion"] != 1:
        raise ProbeError("Unsupported or missing readApiVersion (expected 1)")
    if health.get("authentication") != "loopback":
        raise ProbeError("Unsupported or missing authentication mode")
    if type(health.get("processId")) is not int or health["processId"] <= 0:
        raise ProbeError("Missing or invalid server processId")
    if not isinstance(health.get("database"), str) or not health["database"].strip():
        raise ProbeError("Missing database identity")
    if "clientFingerprint" not in health or (
        health["clientFingerprint"] is not None and not isinstance(health["clientFingerprint"], str)
    ):
        raise ProbeError("Missing or invalid clientFingerprint")
    for flag in ("onlineMail", "adminManagement"):
        if type(health.get(flag)) is not bool:
            raise ProbeError(f"Missing or invalid health flag: {flag}")
    return health["processId"], health["database"], health["clientFingerprint"]


def handshake(base_url=DEFAULT_URL, timeout=5.0):
    base_url = validate_url(base_url)
    if not math.isfinite(timeout) or not 0 < timeout <= 30:
        raise ProbeError("Timeout must be greater than 0 and at most 30 seconds")
    # Do not forward local requests through environment-configured HTTP proxies.
    opener = make_opener()
    health = get_json(opener, base_url, "/gm/tool/health", timeout)
    identity = health_identity(health)
    capabilities = get_json(opener, base_url, "/gm/capabilities", timeout, identity[0])
    if not isinstance(capabilities, dict):
        raise ProbeError("Expected a capabilities object")
    items = capabilities.get("items")
    if not isinstance(items, list) or any(
        not isinstance(item, dict) or not isinstance(item.get("key"), str)
        or type(item.get("implemented")) is not bool for item in items
    ):
        raise ProbeError("Invalid capability list")
    flags = {}
    for flag in ("console", "mail", "content", "strings", "index", "icons", "administration"):
        if type(capabilities.get(flag)) is not bool:
            raise ProbeError(f"Missing or invalid capability flag: {flag}")
        flags[flag] = capabilities[flag]
    # Bind the whole probe to one process, database and resource fingerprint.
    final_health = get_json(opener, base_url, "/gm/tool/health", timeout, identity[0])
    if health_identity(final_health) != identity:
        raise ProbeError("Server identity changed during the probe; reconnect explicitly")
    return health, capabilities


def probe(base_url=DEFAULT_URL, timeout=5.0):
    health, capabilities = handshake(base_url, timeout)
    identity = health_identity(health)
    flags = {flag: capabilities[flag] for flag in
             ("console", "mail", "content", "strings", "index", "icons", "administration")}
    items = capabilities["items"]
    return {
        "status": "compatible",
        "baseUrl": validate_url(base_url),
        "readApiVersion": 1,
        "authentication": "loopback",
        "processId": identity[0],
        "clientFingerprintPresent": bool(identity[2]),
        "resources": flags,
        "capabilityCount": len(items),
        "implementedCapabilityCount": sum(item["implemented"] for item in items),
        "writeEnabled": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_URL)
    parser.add_argument("--timeout", type=float, default=5.0, help="per-request timeout, 0 < seconds <= 30")
    args = parser.parse_args()
    try:
        result = probe(args.base_url, args.timeout)
    except ProbeError as exc:
        print(json.dumps({"status": "unavailable", "error": str(exc), "writeEnabled": False}))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
