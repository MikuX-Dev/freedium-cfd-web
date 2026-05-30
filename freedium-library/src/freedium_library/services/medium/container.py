import os
from urllib.parse import urlparse
from typing import Optional

from dependency_injector import containers, providers

from freedium_library.services.medium.validators import (
    MediumServicePathValidator,
)
from freedium_library.utils.http import CurlRequest
from freedium_library.utils.http.client.config import (
    RequestConfig,
    RequestProxyConfig,
)

from .api import MediumApiService
from .config import MediumConfig
from .medium import MediumService


def _proxy_from_env() -> Optional[RequestProxyConfig]:
    """Build a RequestProxyConfig from the PROXY_LIST env var.

    Format mirrors the legacy convention: comma-separated proxy URLs
    (e.g. ``socks5://haproxy-pb:1080``). HAProxy already load-balances
    across the Warp replicas, so we only consume the first URL — picking
    randomly per request like the legacy code did would just defeat
    HAProxy's session-aware balancing.
    """
    proxy_list = os.environ.get("PROXY_LIST", "").strip()
    if not proxy_list:
        return None

    first = proxy_list.split(",")[0].strip()
    if not first:
        return None

    parsed = urlparse(first)
    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https", "socks5"):
        # Unknown schemes (e.g. socks5h) are skipped silently so a
        # misconfigured env var degrades to "no proxy" rather than crashing.
        return None

    return RequestProxyConfig(
        type=scheme,  # type: ignore[arg-type]
        host=parsed.hostname or "",
        port=parsed.port or (1080 if scheme == "socks5" else 8080),
        username=parsed.username,
        password=parsed.password,
    )


def _build_request_config() -> RequestConfig:
    """Construct a RequestConfig honouring PROXY_LIST if set.

    Kept as a top-level function (rather than inlined into a
    ``providers.Callable``) so unit tests can patch it cleanly and so
    the proxy parsing has a single source of truth.
    """
    return RequestConfig(proxy=_proxy_from_env())


class MediumContainer(containers.DeclarativeContainer):
    config = providers.Singleton(MediumConfig)

    # RequestConfig is built once per container instance; CurlRequest reads
    # config.proxy and threads it through to curl_cffi sessions so all
    # outbound traffic goes via Warp when PROXY_LIST is set.
    request_config = providers.Singleton(_build_request_config)
    request = providers.Singleton(CurlRequest, config=request_config)

    # Injected from outside (CacheContainer.backend or None when CACHE_ENABLED=false).
    # Default to None so unit tests that instantiate MediumContainer in isolation
    # still work without a Mongo.
    cache_backend = providers.Object(None)

    api_service = providers.Singleton(
        MediumApiService,
        request=request,
        config=config,
        cache=cache_backend,
    )
    validator = providers.Singleton(
        MediumServicePathValidator,
        api_service=api_service,
    )
    service = providers.Singleton(
        MediumService,
        request=request,
        api_service=api_service,
        path_validator=validator,
    )
