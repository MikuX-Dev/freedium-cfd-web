from dataclasses import dataclass
from typing import Literal, Optional


@dataclass
class RequestProxyConfig:
    type: Literal["http", "https", "socks5"]
    host: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None

    @property
    def url(self) -> str:
        type = self.type.replace("https", "http")
        proxy_url = f"{type}://"
        if self.username and self.password:
            proxy_url += f"{self.username}:{self.password}@"
        proxy_url += f"{self.host}:{self.port}"
        return proxy_url


@dataclass
class RequestConfig:
    # WARP proxy adds ~5-15s latency to the GraphQL hop. 20s gives
    # enough runway for a typical Medium response through the tunnel
    # while still failing before the uvicorn keepalive/sveltekit fetch
    # timeout (120s). Lower this if you see workers piling up.
    timeout: int = 20
    retries: int = 1  # don't compound the timeout — one shot is enough
    proxy: Optional[RequestProxyConfig] = None
    # backoff_factor: float = 0.1 # not possible. Default value: 0.5. https://github.com/encode/httpx/discussions/1895
