"""
nyt_client.py — NYT Android API client
Reverse-engineered from nyt-android/11.80.0 via mitmproxy capture.

Key findings:
  • API: samizdat-graphql.nytimes.com/graphql/v2  (Apollo GraphQL, APQ)
  • HTTP client stack: okhttp/5.1.0 + apollo-kotlin/4.4.0
  • Auth: NYT-S session cookie (1-year, Domain=.nytimes.com)
  • Paywall: CLIENT-SIDE only — server always returns full article HTML
  • Article body: ~500 KB self-contained HTML inside hybridBody.main.contents
  • Geo-blocking: server enforces Fastly error 703 for non-allowed regions.
    Must use a US/EU proxy/VPN at the network level.
  • nyt-signature: RSA-2048 signed Unix timestamp (private key in Android Keystore).
    Replayed from captured pairs here; rotate the device in WayDroid to regenerate.

Usage:
    client = NYTClient(nyt_s="0^CCASLgib--jR...")   # paste your NYT-S cookie
    feed   = client.home_feed()
    for article in feed:
        print(article["headline"], article["uri"])
        text = client.article_text(article["uri"])
        print(text[:500])
"""

from __future__ import annotations

import base64
import json
import os
import random
import re
import socket
import subprocess
import tempfile
import textwrap
import time
import uuid
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlencode, urlparse

# curl_cffi gives a real browser TLS/HTTP2 fingerprint (impersonate), matching
# the Freedium backend. NYT's edge (DataDome/Akamai) fingerprints clients —
# plain `requests`/`urllib` TLS is flagged — so we impersonate chrome146 over
# HTTP/2, exactly like freedium-library's curl client. API is drop-in
# requests-compatible (Session, get/post, raise_for_status, .json, .cookies).
from curl_cffi import requests

# TLS/HTTP profile — keep in lockstep with freedium-library's curl client.
IMPERSONATE = "chrome146"
HTTP_VERSION = "v2"

# ── Constants ────────────────────────────────────────────────────────────────

GQL_ENDPOINT = "https://samizdat-graphql.nytimes.com/graphql/v2"
CMS_ENDPOINT = "https://samizdat.nytimes.com/cms/mobile/v4/json"
LOGIN_ENDPOINT = "https://myaccount.nytimes.com/svc/android/v1/oauth/login"
SESSION_REFRESH = "https://myaccount.nytimes.com/svc/mobile/v2/session/refresh"

# Apollo Persisted Query hashes (SHA-256), extracted from MITM capture.
# The server only accepts pre-registered query hashes — full query bodies
# are never transmitted on the wire.
APQ_HASHES: dict[str, str] = {
    "AnyWork":                             "dd72bbf1038efcf3509576f7b42361f1656af042e3e57acdcbd42cb9ae6a3e28",
    "OneWebViewHomeQuery":                 "dc6f58e06a4dbf4240a1128ce145b8f8e4289c3a2524fb0520bc1cd3a988b3ec",
    "FeedQuery":                           "c2597607fc8442e98ebd890f2b6d3dcbb201f34ec9bb9625f780cbfd4b2e0cfa",
    "PersonalizedListQuery":               "a2a390000e5ed14e538317990b09a32a6085e21b567ab4171d3fd2cc685d5025",
    "PersonalizedSectionFront":            "f6bb494c9b63e82065c8e5cd73ed255e30599986b584a0e035bcbc3c1775b9bb",
    "SectionFrontLegacyCollection":        "1ef65c66a5f325af5ba0a1020d7e8a66e8711466f8bb7ed8e172277761af0ae2",
    "GetSavedItems":                       "726cb0a696fc5aaf943d2b44014e89cd58aa6326f7d8e8754b9f39b4e42533be",
    "GetUserInterests":                    "189b8b1616c01c8063633bc5831d272eaaa3367948488a97c173d134a203f00b",
    "UserQuery":                           "79a96127e043d767420d83f37f8d909dd3507bba7bbdd038a657ffed73df5aad",
    "UserDetails":                         "NOT_CAPTURED",
    "GamesDestination":                    "04be69b6e798838fb2eb58ef2513c411e8339e6ed4114b5ae65097fb3dcece9d",
    "CookingCollection":                   "56200c571fd3fba1987cc5f87f15baab4956020a85b26c3cbec34b086ab4ee8d",
    "CookingHeroPromoRecipe":              "24cf40e56d6363edfcebfd6fe33cbfc0938bbe931aceb53868e4207e5e00652d",
    "WirecutterXPN":                       "bcbc6ac409b3834e99227cc01bcd4391582436322907feef9982a827024b2397",
    "PromoModule":                         "0803dec7549c46295375e4a39d538da13ced66c9251ed1970f602daf04ba723f",
    "NewsletterSubscriptions":             "afeac96a7fd2fa51f8cb3c2cba1829c014241be6bb404347341eba05fe5349db",
    "LegacyPersonalizedPackagesAppQuery":  "8e69b6a44ae3d9a57ae174e397979395505f07080ab01b641a6473b65fbbd829",
}

# User-Agent strings used by the app (both okhttp native and WebView)
UA_NATIVE  = "okhttp/5.1.0 nyt-android/11.80.0"
UA_WEBVIEW = (
    "Mozilla/5.0 (Linux; Android 13; Build/TQ3A.230901.001; wv) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Version/4.0 Chrome/111.0.5563.116 Mobile Safari/537.36 nyt_android/11.80.0"
)

# Default nyt-token (RSA-2048 public key, base64 DER, from capture).
# Paired with nyt-signature below — both come from the same device.
DEFAULT_NYT_TOKEN = (
    "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAs+/oUCTBmD/cLdmcecrnBMHiU/"
    "pxQCn2DDyaPKUOXxi4p0uUSZQzsuq1pJ1m5z1i0YGPd1U1OeGHAChWtqoxC7bFMCXcwnE1"
    "oyui9G1uobTqWRujG3E2fDv47L7f8x0F23OsNq9GFg7YHLEKfPDpQ0G9hMaTJ7hqK2Q4d8"
    "lbivFfzVpB3MqMZ4t7p+5lQVGhsWX9XaFkZv3JlvqmEFxNnE94V8G2rKGFHAopUYeQVDAQ"
    "AB"
)

# Device UUID that corresponds to DEFAULT_NYT_TOKEN
DEFAULT_AGENT_ID = "b62ba0c0-6134-4d09-935c-2ea58080e34c"

# Realistic Android device descriptors for header rotation. These vary the
# NON-cryptographic metadata (model / OS / screen width) so bulk requests don't
# all look like one device to NYT's analytics / rate-limiter. The nyt-token +
# nyt-signature crypto PAIR is NOT rotated here — fabricating a signature for a
# new token needs the device's private key + the app's (undocumented) signing
# scheme (see README §12.7: rotate the token only by re-capturing). agent-id is
# freshly generated per pick, which is the device-identity the API tracks most.
ANDROID_DEVICE_POOL: list[dict[str, str]] = [
    {"model": "Pixel 8", "os_version": "14", "width": "412"},
    {"model": "Pixel 7a", "os_version": "14", "width": "412"},
    {"model": "Pixel 6", "os_version": "13", "width": "411"},
    {"model": "SM-S918B", "os_version": "14", "width": "384"},   # Galaxy S23 Ultra
    {"model": "SM-S911B", "os_version": "13", "width": "360"},   # Galaxy S23
    {"model": "SM-A546B", "os_version": "13", "width": "384"},   # Galaxy A54
    {"model": "Pixel 8 Pro", "os_version": "14", "width": "448"},
    {"model": "SM-G991B", "os_version": "13", "width": "360"},   # Galaxy S21
    {"model": "moto g power 5G", "os_version": "13", "width": "393"},
    {"model": "OnePlus 11", "os_version": "13", "width": "412"},
]

# ── Extracted RSA-2048 private key (from APK's res/raw/keystore.bks) ─────────
#
# Source: com.nytimes.android.apk → res/raw/keystore.bks
#   Keystore type : BKS (BouncyCastle)
#   Key alias     : "1"
#   Password      : Secrets.ALPHA_PART + BETA_PART + GAMMA_PART (XOR-decoded)
#
# Signing algorithm confirmed from decompiled rhf.java / ia4.java:
#   SHA256withRSA / PKCS1v15
#   Payload = f"{timestamp}\n{url_path}\n{nyt_app_type}\n{app_version}\n"
#
# This makes the client fully self-contained — no WayDroid, no mitmproxy,
# no signature expiry. Fresh signatures are generated per request.

# Secrets are NEVER committed — loaded from env at import:
#   NYT_SIGNING_KEY : base64 DER of the device RSA-2048 PRIVATE key (from the
#                     APK's BKS keystore). Used to sign each request fresh.
#   NYT_S           : optional NYT-S session cookie (unlocks personalized feeds;
#                     NOT needed for article content — paywall is client-side).
# The public nyt-token is DERIVED from the private key, so only one secret.
DEFAULT_NYT_TOKEN = ""
DEFAULT_NYT_S = None  # article content is public (client-side paywall) — no auth
_NYT_PRIVATE_KEY = None
try:
    from cryptography.hazmat.primitives.serialization import (
        load_der_private_key as _load_der,
        Encoding as _Encoding,
        PublicFormat as _PublicFormat,
    )
    from cryptography.hazmat.primitives.asymmetric.padding import PKCS1v15 as _PKCS1v15
    from cryptography.hazmat.primitives.hashes import SHA256 as _SHA256

    _key_b64 = os.environ.get("NYT_SIGNING_KEY", "").strip()
    if _key_b64:
        _NYT_PRIVATE_KEY = _load_der(base64.b64decode(_key_b64), password=None)
        # nyt-token = the matching RSA public key (DER, SubjectPublicKeyInfo).
        DEFAULT_NYT_TOKEN = base64.b64encode(
            _NYT_PRIVATE_KEY.public_key().public_bytes(
                _Encoding.DER, _PublicFormat.SubjectPublicKeyInfo
            )
        ).decode()
except Exception:
    _NYT_PRIVATE_KEY = None  # no key / no cryptography → signing disabled


def _generate_signature(
    url: str,
    app_type: str = "NYT-Phoenix",
    app_version: str = "11.80.0",
) -> tuple[str, str]:
    """
    Generate a fresh ``(nyt-timestamp, nyt-signature)`` pair.

    Signing payload (confirmed from decompiled ``rhf.java``):

    .. code-block:: text

        {unix_timestamp}\n{url_path}\n{nyt_app_type}\n{app_version}\n

    Algorithm: SHA256withRSA / PKCS#1 v1.5 using the key from the APK’s
    embedded BKS keystore (``res/raw/keystore.bks``, alias ``"1"``)
    """
    if _NYT_PRIVATE_KEY is None:
        raise RuntimeError("pip install cryptography to enable signature generation")
    ts      = str(int(time.time()))
    path    = urlparse(url).path
    payload = f"{ts}\n{path}\n{app_type}\n{app_version}\n".encode("utf-8")
    sig     = _NYT_PRIVATE_KEY.sign(payload, _PKCS1v15(), _SHA256())
    return ts, base64.b64encode(sig).decode()

# ── HTML → text extractor ────────────────────────────────────────────────────

class _TextExtractor(HTMLParser):
    """Strip HTML tags, collect visible text from article body."""

    SKIP_TAGS = {"script", "style", "noscript", "head", "nav", "footer",
                 "aside", "figure", "figcaption"}

    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._skip_depth = 0
        self._current_skip: Optional[str] = None

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in self.SKIP_TAGS:
            self._skip_depth += 1
        if tag in ("p", "h1", "h2", "h3", "h4", "li"):
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            stripped = data.strip()
            if stripped:
                self._chunks.append(stripped + " ")

    def get_text(self) -> str:
        raw = "".join(self._chunks)
        # collapse whitespace runs
        return re.sub(r"\n{3,}", "\n\n", re.sub(r" {2,}", " ", raw)).strip()


def html_to_text(html: str) -> str:
    """Extract plain text from NYT article HTML (hybridBody.main.contents)."""
    # Only parse the article body section — skip header/footer noise
    body_match = re.search(
        r'<section[^>]*(?:class|name)="[^"]*(?:articleBody|meteredContent)[^"]*"[^>]*>(.*?)</section>',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    content = body_match.group(1) if body_match else html
    parser = _TextExtractor()
    parser.feed(content)
    return parser.get_text()


# ── NYTClient ────────────────────────────────────────────────────────────────

class NYTClient:
    """
    Minimal NYT Android API client.

    Authentication
    --------------
    The server enforces a metered paywall CLIENT-SIDE — the full article HTML
    is always delivered by the API regardless of auth state. However, providing
    a valid NYT-S cookie unlocks personalized feeds, saved items, and avoids
    any server-side rate limiting.

    To get a NYT-S cookie:
        1. Log in to nytimes.com in a browser and copy the NYT-S cookie.
        2. Use NYTClient.login_google() if you have a Google OAuth token.
        3. Run without a cookie — unauthenticated requests still return
           full article content (paywall is client-side only).

    Parameters
    ----------
    nyt_s : str, optional
        Value of the NYT-S session cookie. Long-lived (1 year).
    nyt_token : str, optional
        Device RSA-2048 public key (base64 DER). Defaults to key from capture.
    prop : str
        Property identifier. "droidapp" (phone) or "drtabapp" (tablet).
    plat : str
        Platform string. "phone" or "tablet".
    """

    def __init__(
        self,
        nyt_s: Optional[str] = DEFAULT_NYT_S,
        nyt_token: str = DEFAULT_NYT_TOKEN,
        agent_id: str = DEFAULT_AGENT_ID,
        prop: str = "droidapp",
        plat: str = "phone",
        device_model: str = "Waydroid WayDroid x86_64 Device",
        os_version: str = "13",
        device_width: str = "412",
        proxy: Optional[str] = None,
        rotate_devices: bool = False,
    ) -> None:
        self.nyt_s = nyt_s
        self.prop = prop
        self.plat = plat
        self._agent_id = agent_id
        self.device_model = device_model
        self.os_version = os_version
        self.device_width = device_width
        # When True, each request advertises a different (random) Android device
        # descriptor + a fresh agent-id, so bulk fetches don't all look like one
        # device. The token/signature pair stays fixed (see ANDROID_DEVICE_POOL).
        self.rotate_devices = rotate_devices
        # Pick the most recent captured signature as default
        _ts, _sig = _generate_signature(GQL_ENDPOINT)
        self._sig_ts = _ts
        self._sig_val = _sig
        self.device_type = "android_tablet" if plat == "tablet" else "android_phone"
        
        # NYT's API edge 403s datacenter IPs; route through a residential/mobile
        # proxy when given (e.g. "http://user:pass@host:port" or socks5h://...).
        proxies = {"http": proxy, "https": proxy} if proxy else None
        self._session = requests.Session(
            impersonate=IMPERSONATE,
            http_version=HTTP_VERSION,
            proxies=proxies,
        )
        self._session.headers.update({
            # ── Transport ─────────────────────────────────────────────
            "User-Agent":     UA_NATIVE,
            "Accept":         "multipart/mixed;deferSpec=20220824, application/graphql-response+json, application/json",
            "Accept-Encoding": "gzip",
            # ── Device identity (fixed per client instance) ─────────────
            "nyt-token":        nyt_token,
            "nyt-app-type":     "NYT-Phoenix",
            "nyt-app-version":  "11.80.0",
            "nyt-build-type":   "release",
            # ── Apollo ───────────────────────────────────────────
            "apollo-require-preflight": "true",
        })
        if nyt_s:
            self._session.cookies.set("NYT-S", nyt_s, domain=".nytimes.com")

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _device_headers(self) -> dict[str, str]:
        """Device-descriptor headers, emitted per request. With rotate_devices
        they vary across ANDROID_DEVICE_POOL + a fresh agent-id each call;
        otherwise the client's fixed device values are used. Non-cryptographic
        only — the nyt-token/nyt-signature pair is unaffected."""
        if self.rotate_devices:
            d = random.choice(ANDROID_DEVICE_POOL)
            model, os_version, width = d["model"], d["os_version"], d["width"]
            agent_id = str(uuid.uuid4())
        else:
            model, os_version, width = self.device_model, self.os_version, self.device_width
            agent_id = self._agent_id
        return {
            "nyt-agent-id":     agent_id,
            "nyt-device-model": model,
            "nyt-device-type":  self.device_type,
            "nyt-os-version":   os_version,
            "nyt-device-width": width,
        }

    def _gql(
        self,
        operation: str,
        variables: dict,
        timeout: int = 30,
    ) -> dict:
        """
        Execute an Apollo Persisted Query against the samizdat-graphql endpoint.

        The app never sends the full query body — only the SHA-256 hash of a
        server-side pre-registered query (APQ pattern). If the hash is unknown
        to the server it returns a 200 with {"errors":[{"message":"PersistedQueryNotFound"}]}.

        Required headers (all must be present or server returns 403):
          nyt-signature  — RSA-2048 signed timestamp (replayed from capture)
          nyt-timestamp  — Unix timestamp matching the signature
          nyt-agent-id   — device UUID
          nyt-app-type / nyt-app-version / nyt-build-type
          nyt-device-model / nyt-device-type / nyt-os-version
          apollo-require-preflight
          x-apollo-operation-id / x-apollo-operation-name

        NOTE: The server geo-blocks non-US/EU IPs (Fastly error 703).
              Route through a US/EU proxy at the network level.
        """
        if operation not in APQ_HASHES:
            raise ValueError(f"Unknown operation '{operation}'. Known: {list(APQ_HASHES)}")

        apq_hash = APQ_HASHES[operation]
        extensions = {
            "persistedQuery": {
                "version": 1,
                "sha256Hash": apq_hash,
            },
            "clientLibrary": {
                "name": "apollo-kotlin",
                "version": "4.4.0",
            },
        }

        params = {
            "operationName": operation,
            "variables": json.dumps(variables, separators=(",", ":")),
            "extensions": json.dumps(extensions, separators=(",", ":")),
        }

        # Generate a fresh signature for each request
        ts, sig = _generate_signature(GQL_ENDPOINT)
        extra_headers = {
            "nyt-timestamp":          ts,
            "nyt-signature":          sig,
            "x-apollo-operation-id":  apq_hash,      # operation-id == apq sha256 hash
            "x-apollo-operation-name": operation,
            **self._device_headers(),
            # The full endpoint URL is also sent as a header by the app
            "x-nyt-graphql-endpoint": (
                GQL_ENDPOINT + "?operationName=" + operation
                + "&variables=" + params["variables"]
            )[:500],
        }

        resp = self._session.get(
            GQL_ENDPOINT, params=params, headers=extra_headers, timeout=timeout
        )

        if resp.status_code == 403:
            trace = resp.headers.get("trace", "")
            if "703" in trace or "403" in trace:
                # Expired signature — auto-refresh and retry once
                try:
                    self.refresh_signature()
                    extra_headers["nyt-timestamp"] = self._sig_ts
                    extra_headers["nyt-signature"] = self._sig_val
                    resp = self._session.get(
                        GQL_ENDPOINT, params=params, headers=extra_headers, timeout=timeout
                    )
                    if resp.status_code != 200:
                        resp.raise_for_status()
                except Exception as refresh_err:
                    raise PermissionError(
                        f"403 on {operation} and auto-refresh failed: {refresh_err}\n"
                        f"  Run WayDroid + NYT app, then retry."
                    ) from refresh_err

        resp.raise_for_status()
        data = resp.json()

        if "errors" in data:
            raise RuntimeError(f"GraphQL errors for {operation}: {data['errors']}")

        return data.get("data", {})

    def set_signature(self, timestamp: str, signature: str) -> None:
        """
        Override the captured (timestamp, signature) pair.

        Use this to inject a freshly captured signature from a new WayDroid
        MITM session. The server validates the signature using the RSA public
        key in the nyt-token header, so token + signature must come from the
        same device.

        Parameters
        ----------
        timestamp : str
            Unix timestamp string, e.g. "1782201957"
        signature : str
            Base64-encoded RSA-2048 signature of that timestamp.
        """
        self._sig_ts = timestamp
        self._sig_val = signature

    def refresh_signature(self, timeout: int = 30) -> None:
        """
        Capture a fresh ``nyt-signature`` by intercepting live WayDroid traffic.

        Workflow
        --------
        1. Writes a one-shot mitmdump addon to ``/tmp/nyt_sig_addon.py``.
        2. Starts ``mitmdump`` as a regular HTTP proxy on a free local port.
        3. Configures the WayDroid Android system proxy to that port via ``adb``.
        4. Wakes the NYT app (``am start``) so it makes a network request.
        5. Waits up to *timeout* seconds for the addon to write
           ``/tmp/nyt_fresh_sig.json``.
        6. Restores the original WayDroid proxy setting.
        7. Updates ``self._sig_ts`` / ``self._sig_val`` in-place.

        Requirements
        ------------
        - ``mitmdump`` on ``$PATH``  (``pip install mitmproxy``)
        - ``adb`` on ``$PATH`` with the WayDroid container reachable
        - WayDroid running with the NYT app installed

        Raises
        ------
        TimeoutError
            If no signature was captured within *timeout* seconds.
        RuntimeError
            If ``mitmdump`` or ``adb`` are not found on PATH.
        """
        SIG_FILE = "/tmp/nyt_fresh_sig.json"
        ADDON_FILE = "/tmp/nyt_sig_addon.py"

        # ── 1. Write inline mitmdump addon ────────────────────────────────────
        addon_src = textwrap.dedent("""\
            import json
            from mitmproxy import http

            _done = False

            def request(flow: http.HTTPFlow):
                global _done
                if _done:
                    return
                h = flow.request.headers
                sig = h.get("nyt-signature", "")
                ts  = h.get("nyt-timestamp", "")
                if sig and ts and "samizdat-graphql" in flow.request.pretty_url:
                    import json
                    with open("/tmp/nyt_fresh_sig.json", "w") as f:
                        json.dump({"timestamp": ts, "signature": sig,
                                   "nyt_s": h.get("cookie", "").replace("NYT-S=", "").split(";")[0]}, f)
                    _done = True
        """)
        Path(ADDON_FILE).write_text(addon_src)
        if Path(SIG_FILE).exists():
            Path(SIG_FILE).unlink()

        # ── 2. Find a free port ───────────────────────────────────────────────
        with socket.socket() as s:
            s.bind(("", 0))
            port = s.getsockname()[1]

        # ── 3. Start mitmdump ─────────────────────────────────────────────────
        try:
            proc = subprocess.Popen(
                ["mitmdump", "--mode", f"regular@{port}", "-s", ADDON_FILE, "-q"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            raise RuntimeError(
                "mitmdump not found. Install with: pip install mitmproxy"
            )
        time.sleep(1)  # let mitmdump bind

        # ── 4. Configure WayDroid proxy via adb ───────────────────────────────
        _adb = lambda *args: subprocess.run(
            ["adb", "shell", *args],
            capture_output=True, timeout=8,
        )
        old_proxy = ""
        try:
            r = _adb("settings", "get", "global", "http_proxy")
            old_proxy = r.stdout.decode().strip()
        except Exception:
            pass

        try:
            _adb("settings", "put", "global", "http_proxy", f"127.0.0.1:{port}")
            # Wake the NYT app — triggers a background network call
            _adb("am", "start", "-n",
                 "com.nytimes.android/com.nytimes.android.activity.MainActivity")

            # ── 5. Wait for signature file ────────────────────────────────────
            deadline = time.time() + timeout
            while time.time() < deadline:
                if Path(SIG_FILE).exists():
                    data = json.loads(Path(SIG_FILE).read_text())
                    self._sig_ts  = data["timestamp"]
                    self._sig_val = data["signature"]
                    # Also update NYT-S if the app sent one
                    fresh_nyt_s = data.get("nyt_s", "")
                    if fresh_nyt_s and fresh_nyt_s != self.nyt_s:
                        self.nyt_s = fresh_nyt_s
                        self._session.cookies.set("NYT-S", fresh_nyt_s,
                                                  domain=".nytimes.com")
                    return
                time.sleep(0.4)

            raise TimeoutError(
                f"No nyt-signature captured in {timeout}s.\n"
                f"  Make sure WayDroid is running and the NYT app is installed."
            )
        finally:
            proc.terminate()
            # ── 6. Restore original WayDroid proxy ───────────────────────────
            try:
                if old_proxy and old_proxy != "null":
                    _adb("settings", "put", "global", "http_proxy", old_proxy)
                else:
                    _adb("settings", "delete", "global", "http_proxy")
            except Exception:
                pass

    def load_signatures_from_mitm(self, mitm_path: str) -> int:
        """
        Extract ``(timestamp, signature)`` pairs from an existing ``.mitm``
        capture file and update this client instance.

        Use this for the manual workflow: run the NYT app under mitmproxy,
        save the capture, then call this instead of ``refresh_signature()``.

        Parameters
        ----------
        mitm_path : str
            Path to a ``.mitm`` file produced by ``mitmdump -w <file>``.

        Returns
        -------
        int
            Number of unique ``(timestamp, signature)`` pairs loaded.

        Raises
        ------
        ImportError
            If ``mitmproxy`` is not installed.
        """
        try:
            from mitmproxy.io import FlowReader
        except ImportError:
            raise ImportError("pip install mitmproxy")

        pairs: dict[str, str] = {}
        latest_nyt_s = ""
        with open(mitm_path, "rb") as fh:
            for flow in FlowReader(fh).stream():
                try:
                    url = flow.request.pretty_url
                    if "samizdat-graphql" not in url:
                        continue
                    h   = flow.request.headers
                    ts  = h.get("nyt-timestamp", "")
                    sig = h.get("nyt-signature", "")
                    if ts and sig:
                        pairs[ts] = sig
                    nyt_s = h.get("cookie", "").replace("NYT-S=", "").split(";")[0].strip()
                    if nyt_s:
                        latest_nyt_s = nyt_s
                except Exception:
                    continue

        if not pairs:
            raise ValueError(f"No nyt-signature headers found in {mitm_path}")

        # Update to the freshest captured pair
        ts, sig = max(pairs.items(), key=lambda x: int(x[0]))
        self._sig_ts  = ts
        self._sig_val = sig
        if latest_nyt_s:
            self.nyt_s = latest_nyt_s
            self._session.cookies.set("NYT-S", latest_nyt_s, domain=".nytimes.com")
        return len(pairs)

    def _platform_vars(self) -> dict:
        """Common platform context variables sent with most operations."""
        return {
            "prop": self.prop,
            "edn": "us",
            "plat": self.plat,
            "ver": "android",
        }

    # ── Authentication ────────────────────────────────────────────────────────

    @classmethod
    def login_google(
        cls,
        google_oauth_token: str,
        agent_id: Optional[str] = None,
        **kwargs,
    ) -> "NYTClient":
        """
        Exchange a Google OAuth2 access token for a NYT-S session cookie.

        Parameters
        ----------
        google_oauth_token : str
            A valid Google OAuth2 access_token with `profile email` scope.
            Obtain via Google Sign-In SDK or the web OAuth flow:
              client_id: 1005640118348-amh5tgkq641oru4fbhr3psm3gt2tcc94.apps.googleusercontent.com
              redirect_uri: https://myaccount.nytimes.com/google-client-callback/news
              scope: profile email
        agent_id : str, optional
            A stable device UUID. Generated fresh if not provided.

        Returns
        -------
        NYTClient
            Authenticated client instance.
        """
        if agent_id is None:
            agent_id = str(uuid.uuid4())

        # myaccount.nytimes.com is DataDome-protected; impersonate so the TLS
        # fingerprint matches a real client (same profile as the content path).
        s = requests.Session(impersonate=IMPERSONATE, http_version=HTTP_VERSION)
        s.headers["User-Agent"] = UA_NATIVE

        # Step 1: POST Google token to NYT OAuth endpoint
        resp = s.post(
            LOGIN_ENDPOINT,
            data={
                "provider": "google",
                "agentID": agent_id,
                "token": google_oauth_token,
            },
            timeout=15,
        )
        resp.raise_for_status()

        # Step 2: Refresh session to obtain the long-lived NYT-S cookie
        refresh = s.post(SESSION_REFRESH, timeout=15)
        refresh.raise_for_status()

        nyt_s = refresh.cookies.get("NYT-S")
        if not nyt_s:
            raise RuntimeError(
                "Session refresh did not set NYT-S cookie. "
                "Login may have failed. "
                f"Login status: {resp.status_code}, Refresh status: {refresh.status_code}"
            )

        return cls(nyt_s=nyt_s, **kwargs)

    def refresh_session(self) -> str:
        """Rotate the NYT-S session token. Returns new token value."""
        resp = self._session.post(SESSION_REFRESH, timeout=15)
        resp.raise_for_status()
        new_token = resp.cookies.get("NYT-S")
        if new_token:
            self.nyt_s = new_token
            self._session.cookies.set("NYT-S", new_token, domain=".nytimes.com")
        return self.nyt_s

    # ── Home feed ─────────────────────────────────────────────────────────────

    def home_feed(self) -> list[dict]:
        """
        Fetch the home page feed (OneWebViewHomeQuery, ~1.8 MB response).

        Returns a flat list of article stubs, each with:
            uri      : "nyt://article/<UUID>"
            headline : str
            summary  : str
            url      : str  (public URL)
            section  : str
        """
        data = self._gql(
            "OneWebViewHomeQuery",
            {"id": "/root-home-node-onewebview"},
        )
        return self._parse_feed_response(data)

    def section_feed(self, section: str) -> list[dict]:
        """
        Fetch articles for a named section.

        Parameters
        ----------
        section : str
            Section name, e.g. "sports", "business", "technology", "opinion".
        """
        data = self._gql(
            "SectionFrontLegacyCollection",
            {"id": f"section/{section}", "count": 40, **self._platform_vars()},
        )
        return self._parse_feed_response(data)

    def opinion_feed(self) -> list[dict]:
        """Fetch the Opinion section feed."""
        data = self._gql("FeedQuery", {"url": "/feed/opinion/"})
        return self._parse_feed_response(data)

    def personalized_feed(self, list_uri: str, count: int = 14) -> list[dict]:
        """
        Fetch a personalized list (requires authenticated NYT-S cookie).

        Parameters
        ----------
        list_uri : str
            e.g. "nyt://per/personalized-list/xpn-athletic"
        """
        data = self._gql(
            "PersonalizedListQuery",
            {"listUri": list_uri, "first": count, "useGenericFallback": False},
        )
        return self._parse_feed_response(data)

    def _parse_feed_response(self, data: dict) -> list[dict]:
        """
        Walk the deeply-nested GraphQL feed response and extract article stubs.

        NYT's feed schema is a recursive tree of "containers", "collections",
        "assets", and "items". We extract any node with a "uri" that starts
        with "nyt://article/".
        """
        articles: list[dict] = []
        self._walk(data, articles)
        # deduplicate by URI
        seen: set[str] = set()
        unique: list[dict] = []
        for a in articles:
            if a["uri"] not in seen:
                seen.add(a["uri"])
                unique.append(a)
        return unique

    def _walk(self, node: Any, out: list[dict]) -> None:
        """Recursively walk nested dicts/lists to find article stubs."""
        if isinstance(node, dict):
            uri = node.get("uri", "")
            typename = node.get("__typename", "")
            if (
                uri.startswith("nyt://article/")
                and typename in ("Article", "AthleticArticle", "")
            ):
                out.append({
                    "uri": uri,
                    "headline": (
                        (node.get("headline") or {}).get("default") or
                        (node.get("headline") or {}).get("seo") or ""
                    ),
                    "summary": node.get("summary") or node.get("abstract") or "",
                    "url": node.get("url") or "",
                    "section": (
                        (node.get("section") or {}).get("displayName") or
                        node.get("sectionName") or ""
                    ),
                    "desk": node.get("desk") or "",
                    "byline": (
                        node.get("bylines", [{}])[0].get("renderedRepresentation", "")
                        if node.get("bylines") else ""
                    ),
                    "lastModified": node.get("lastModified") or node.get("lastMajorModification") or "",
                    "sourceId": node.get("sourceId") or "",
                })
            for v in node.values():
                self._walk(v, out)
        elif isinstance(node, list):
            for item in node:
                self._walk(item, out)

    # ── Article fetching ──────────────────────────────────────────────────────

    # ── URL → UUID resolution ─────────────────────────────────────────────────

    def resolve_url(self, url: str) -> str:
        """
        Resolve a public NYT article URL to its internal ``nyt://article/<UUID>`` URI.

        Strategy: fetch the public article page and extract the
        ``<meta property="al:android:url">`` App Links tag, which the
        server embeds for Android deep linking. This tag contains the
        canonical ``nyt://article/<UUID>`` URI.

        Parameters
        ----------
        url : str
            Public article URL, e.g.:
            ``https://www.nytimes.com/2026/06/22/us/politics/jd-vance-iran-negotiations.html``

        Returns
        -------
        str
            ``nyt://article/<UUID>`` URI.

        Raises
        ------
        ValueError
            If the page does not contain the App Links meta tag (e.g. not an
            article, or the page is paywalled at the CDN level).
        """
        # Use a browser UA so the page renders its meta tags
        resp = self._session.get(
            url,
            headers={"User-Agent": UA_WEBVIEW, "Accept": "text/html"},
            timeout=20,
        )
        resp.raise_for_status()
        # Fast regex scan — no need to parse full HTML
        m = re.search(
            r'<meta[^>]+property=["\']al:android:url["\'][^>]+content=["\']([^"\'>]+)["\']',
            resp.text,
        ) or re.search(
            r'<meta[^>]+content=["\']([^"\'>]+)["\'][^>]+property=["\']al:android:url["\']',
            resp.text,
        )
        if not m:
            # Fallback: look for nyt://article/ anywhere on the page
            m2 = re.search(r'nyt://article/([0-9a-f-]{36})', resp.text)
            if m2:
                return f"nyt://article/{m2.group(1)}"
            raise ValueError(
                f"Could not find nyt:// URI in {url}\n"
                f"  Page length: {len(resp.text)} chars\n"
                f"  HTTP status: {resp.status_code}\n"
                f"  Tip: ensure your proxy/VPN is active so the page loads fully."
            )
        return m.group(1)  # e.g. "nyt://article/bb680e91-aae3-59b1-9207-401dbc75bd98"

    def _normalize_uri(self, uri_or_url: str) -> str:
        """
        Accept any of the following and return a URI that ``AnyWork`` accepts:

          • ``nyt://article/<UUID>``       → returned as-is
          • ``<UUID>``  (bare UUID)        → wrapped as ``nyt://article/<UUID>``
          • ``https://www.nytimes.com/…``  → returned as-is (AnyWork resolves it server-side)
        """
        s = uri_or_url.strip()
        if s.startswith("nyt://") or s.startswith("http://") or s.startswith("https://"):
            return s
        # bare UUID
        return f"nyt://article/{s}"

    # ── Article fetching ──────────────────────────────────────────────────────

    def article_raw(
        self,
        uri: str,
        prop: Optional[str] = None,
        plat: Optional[str] = None,
    ) -> dict:
        """
        Fetch the full AnyWork GraphQL response for a single article.

        Parameters
        ----------
        uri : str
            Any of:
              • ``nyt://article/36b67561-134b-5078-ac23-d8a270ff86e2``
              • ``36b67561-134b-5078-ac23-d8a270ff86e2``  (bare UUID)
              • ``https://www.nytimes.com/2026/06/22/us/politics/jd-vance-iran-negotiations.html``

            Full HTTPS URLs are passed directly to the GraphQL server, which
            resolves them internally — no HTML scraping required.

        Returns
        -------
        dict
            The ``data.anyWork`` GraphQL object:  __typename, headline,
            bylines, desk, summary, section, hybridBody.main.contents
            (full HTML ~500 KB), adTargetingParams, sourceId, url, uri,
            lastModified, ...
        """
        nyt_uri = self._normalize_uri(uri)

        data = self._gql(
            "AnyWork",
            {
                "uri": nyt_uri,
                "prop": prop or self.prop,
                "edn": "us",
                "plat": plat or self.plat,
                "ver": "android",
            },
        )
        return data.get("anyWork") or {}

    # Structured-body query (NOT a persisted hash). The server accepts custom
    # GraphQL (APQ allowlist isn't enforced), so we request the typed body
    # blocks — which include inline ImageBlocks WITH full crop URLs. The
    # persisted AnyWork query only returns pre-rendered hybridBody HTML where
    # inline images are JS-lazy placeholders (no URLs). This is how we get
    # every body image server-side.
    _STRUCTURED_QUERY = (
        "query($id: String!) { anyWork(id: $id) { __typename"
        " ... on Article {"
        "   headline { default } summary"
        "   bylines { renderedRepresentation creators { __typename ... on Person { displayName description promotionalMedia { __typename ... on Image { crops { renditions { url width } } } } } } }"
        "   section { displayName }"
        "   lastMajorModification"
        # hybridBody carries the rendered #enhanced-byline (short per-article
        # author bio + datelines) — not present as a structured field/block.
        "   hybridBody { main { contents } }"
        "   promotionalMedia { __typename ... on Image { caption { text } crops { renditions { url width } } } }"
        "   body { content {"
        "     __typename"
        "     ... on ParagraphBlock { content { __typename ... on TextInline { text formats { __typename ... on LinkFormat { url } } } } }"
        "     ... on Heading2Block { content { ... on TextInline { text } } }"
        "     ... on ImageBlock { media { __typename ... on Image { caption { text } credit crops { renditions { url width } } } } }"
        # Custom NYT layouts: image grid + side-by-side diptych. (media is
        # aliased to gridMedia — ImageBlock.media is Image, GridBlock.media is
        # [GridBlockMedia], so the same field name would otherwise conflict.)
        "     ... on GridBlock { gridMedia: media { __typename ... on Image { caption { text } credit crops { renditions { url width } } } } }"
        "     ... on DiptychBlock {"
        "       imageOne { __typename ... on Image { caption { text } credit crops { renditions { url width } } } }"
        "       imageTwo { __typename ... on Image { caption { text } credit crops { renditions { url width } } } }"
        "     }"
        "   } }"
        " } } }"
    )

    def article_structured(self, uri: str) -> dict:
        """Fetch the article via a custom GraphQL query that returns the typed
        body blocks (paragraphs, headings, ImageBlocks with full crop URLs) —
        unlike the persisted AnyWork query whose hybridBody HTML lazy-loads
        inline images. Returns the ``anyWork`` Article object (or {})."""
        nyt_uri = self._normalize_uri(uri)
        ts, sig = _generate_signature(GQL_ENDPOINT)
        headers = {
            **self._device_headers(),
            "nyt-timestamp": ts,
            "nyt-signature": sig,
            "content-type": "application/json",
        }
        resp = self._session.post(
            GQL_ENDPOINT,
            json={"query": self._STRUCTURED_QUERY, "variables": {"id": nyt_uri}},
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return (data.get("data") or {}).get("anyWork") or {}

    def article_html(self, uri: str) -> str:
        """
        Return the raw HTML of an article (hybridBody.main.contents).

        This is a complete, self-contained HTML document (~500 KB) that the app
        renders inside a WebView. The paywall div is present but unenforced —
        all paragraphs are in the HTML regardless of subscription status.

        The paywall marker: <section class="meteredContent" data-paywall-inert="">
        The JS that enforces it never runs in our context.
        """
        raw = self.article_raw(uri)
        try:
            return raw["hybridBody"]["main"]["contents"]
        except (KeyError, TypeError):
            raise ValueError(
                f"No hybridBody in response for {uri}. "
                f"typename={raw.get('__typename')}"
            )

    def article_text(self, uri: str) -> str:
        """
        Fetch an article and return its full plain text.

        Bypasses the client-side paywall naturally — the HTML always contains
        all paragraphs; we just strip the tags.
        """
        html = self.article_html(uri)
        return html_to_text(html)

    def article_meta(self, uri: str) -> dict:
        """
        Fetch article metadata without the full HTML body.

        Returns a dict with: headline, byline, desk, section, summary,
        slug, url, sourceId, lastModified, commentStatus, adParams.
        """
        raw = self.article_raw(uri)
        return {
            "uri": raw.get("uri"),
            "url": raw.get("url"),
            "slug": raw.get("slug"),
            "sourceId": raw.get("sourceId"),
            "headline": (raw.get("headline") or {}).get("default", ""),
            "headline_seo": (raw.get("headline") or {}).get("seo", ""),
            "byline": (
                raw["bylines"][0].get("renderedRepresentation", "")
                if raw.get("bylines") else ""
            ),
            "desk": raw.get("desk"),
            "section": (raw.get("section") or {}).get("displayName"),
            "summary": raw.get("summary"),
            "lastModified": raw.get("lastModified"),
            "lastMajorModification": raw.get("lastMajorModification"),
            "kicker": raw.get("kicker"),
            "commentStatus": (raw.get("commentProperties") or {}).get("status"),
            "adSensitivity": (raw.get("advertisingProperties") or {}).get("sensitivity"),
            "featuredAudio": (raw.get("featuredAudio") or {}).get("asset", {}).get("uri"),
            "adTargetingParams": {
                p["key"]: p["value"]
                for p in (raw.get("adTargetingParams") or [])
            },
        }

    # ── Legacy CMS feed ───────────────────────────────────────────────────────

    def latest_feed_legacy(self, form_factor: str = "android") -> dict:
        """
        Fetch the legacy Samizdat CMS JSON feed.

        This is an unauthenticated public endpoint used as a fallback.

        Parameters
        ----------
        form_factor : str
            "android" (phone) or "android_tablet"
        """
        url = f"{CMS_ENDPOINT}/{form_factor}/latestfeed.json"
        resp = self._session.get(
            url,
            params={"did": "", "template": "hybrid"},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    # ── User / account ────────────────────────────────────────────────────────

    def user_details(self) -> dict:
        """Fetch account details (requires authenticated NYT-S)."""
        return self._gql("UserQuery", {})

    def saved_items(self, count: int = 50) -> list[dict]:
        """Fetch saved/bookmarked articles (requires authenticated NYT-S)."""
        data = self._gql(
            "GetSavedItems",
            {
                "input": {
                    "first": count,
                    "itemTypes": [
                        "ARTICLE", "INTERACTIVE", "SLIDESHOW",
                        "LEGACY_COLLECTION", "STORYLINE",
                    ],
                }
            },
        )
        return self._parse_feed_response(data)

    def user_interests(self) -> dict:
        """Fetch personalized interest graph (requires authenticated NYT-S)."""
        return self._gql("GetUserInterests", {})

    # ── Games ─────────────────────────────────────────────────────────────────

    def games_active(self, date: Optional[str] = None) -> dict:
        """
        Fetch active puzzles for a given date.

        Parameters
        ----------
        date : str, optional
            ISO date string "YYYY-MM-DD". Defaults to today.
        """
        if date is None:
            date = time.strftime("%Y-%m-%d")
        resp = self._session.get(
            "https://www.nytimes.com/svc/games/v1/puzzles/active.json",
            params={"date": date},
            headers={"User-Agent": UA_WEBVIEW},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def games_progress(self, **puzzle_ids) -> dict:
        """
        Fetch solve progress for specific puzzles (requires NYT-S).

        Parameters
        ----------
        **puzzle_ids : int
            Puzzle type → ID mapping, e.g.:
            games_progress(crossword_daily=24115, spelling_bee=21619, wordle=208)
        """
        resp = self._session.get(
            "https://www.nytimes.com/svc/games/v1/puzzles/progress.json",
            params=puzzle_ids,
            headers={"User-Agent": UA_WEBVIEW},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    # ── Cooking ───────────────────────────────────────────────────────────────

    def cooking_collection(self) -> list[dict]:
        """Fetch the Cooking section feed."""
        data = self._gql(
            "CookingCollection",
            {
                "id": "/syndicated/xpn-panel-cooking",
                "promoModuleId": "",
                "includePromoModule": False,
            },
        )
        return self._parse_feed_response(data)

    def cooking_recipe(self, recipe_url: str) -> dict:
        """
        Fetch a Cooking recipe's hero/promo data.

        Parameters
        ----------
        recipe_url : str
            Full recipe URL, e.g.:
            "https://cooking.nytimes.com/recipes/781623159-greek-salad-with-sardines-and-beans"
        """
        data = self._gql(
            "CookingHeroPromoRecipe",
            {"assetID": recipe_url},
        )
        return data

    # ── Wirecutter ────────────────────────────────────────────────────────────

    def wirecutter_feed(self) -> list[dict]:
        """Fetch the Wirecutter (product reviews) section feed."""
        data = self._gql(
            "WirecutterXPN",
            {"promoModuleId": "", "includePromoModule": False},
        )
        return self._parse_feed_response(data)

    # ── Convenience ───────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        auth = "authenticated" if self.nyt_s else "unauthenticated"
        return f"<NYTClient {auth} prop={self.prop!r} plat={self.plat!r}>"
