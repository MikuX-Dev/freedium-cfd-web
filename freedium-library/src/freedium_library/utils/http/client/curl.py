import warnings
from types import TracebackType
from typing import Any, Dict, Literal, Optional, Type

from curl_cffi.requests import Session, AsyncSession

from .abstract import AbstractRequest
from .config import RequestConfig
from .curl_response import CurlResponse
from .response import AbstractResponse


class CurlRequest(AbstractRequest):
    __slots__ = ("config", "_in_context_manager", "_session", "_async_session", "_impersonate", "_http_version", "_persistent")

    def __init__(
        self,
        config: Optional[RequestConfig] = None,
        impersonate: str = "chrome146",
        persistent: bool = False,
    ):
        """`persistent=True` marks a deliberately long-lived client — one owned
        by a singleton service and reused for the process lifetime, so its
        session and connection pool survive across requests. It opts out of the
        context-manager warnings, which exist to catch *accidental* misuse."""
        self.config = config or RequestConfig()
        self._persistent = persistent
        self._in_context_manager = False
        self._session: Any = None
        self._async_session: Any = None
        self._impersonate: str = impersonate
        self._http_version: Literal["v2"] = "v2"  # H2 over WARP TCP; H3 (QUIC) breaks through SOCKS5
        # NB: no warning here. Constructing a client is legitimate — misuse is
        # only detectable at request time, which `_check_context_manager` does.
        # Warning in __init__ fired on every correctly-written `async with` too.

    @property
    def _proxies(self) -> Optional[Dict[str, str]]:
        # curl_cffi accepts a proxies dict keyed by scheme. We mirror the
        # same URL into both http/https so SOCKS5 proxies (which front both)
        # work without the caller having to think about it.
        if self.config.proxy is None:
            return None
        url = self.config.proxy.url
        return {"http": url, "https": url}

    def _get_session(self) -> Any:
        if not self._session:
            self._session = Session(impersonate=self._impersonate, http_version=self._http_version, proxies=self._proxies)
        return self._session

    async def _get_async_session(self) -> Any:
        if not self._async_session:
            self._async_session = AsyncSession(impersonate=self._impersonate, http_version=self._http_version, proxies=self._proxies)
        return self._async_session

    def __enter__(self) -> "CurlRequest":
        self._in_context_manager = True
        self._session = Session(impersonate=self._impersonate, http_version=self._http_version, proxies=self._proxies)
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        if self._session:
            self._session.close()
        self._session = None

    async def __aenter__(self) -> "CurlRequest":
        self._in_context_manager = True
        self._async_session = AsyncSession(impersonate=self._impersonate, http_version=self._http_version, proxies=self._proxies)
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        if self._async_session:
            await self._async_session.close()
        self._async_session = None

    def __del__(self):
        if self._session:
            self._session.close()
        if self._async_session and not self._persistent:
            # An async session can't be awaited closed from __del__, so it can
            # only be reported. Reaching here means a caller built the client
            # and issued async requests without `async with` — the session's
            # connections leak until the process exits. Surface it rather than
            # failing silently. (Persistent clients are exempt: living for the
            # process lifetime is the point.)
            warnings.warn(
                "CurlRequest garbage-collected with an open async session — "
                "its connections leaked. Use 'async with' at the call site.",
                ResourceWarning,
                stacklevel=2,
            )

    def _check_context_manager(self):
        if not self._in_context_manager and not self._persistent:
            warnings.warn(
                "Request is not being used as a context manager. This may lead to "
                "resource leaks. Use 'with' or 'async with' statement.",
                stacklevel=2,
            )

    def get(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        follow_redirects: bool = True,
    ) -> AbstractResponse:
        self._check_context_manager()
        session = self._get_session()
        response = session.get(
            url,
            params=params,
            headers=headers,
            allow_redirects=follow_redirects,
            timeout=self.config.timeout,
        )
        return CurlResponse(response)

    def post(
        self,
        url: str,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        follow_redirects: bool = True,
    ) -> AbstractResponse:
        self._check_context_manager()
        session = self._get_session()
        response = session.post(
            url,
            json=data,
            headers=headers,
            allow_redirects=follow_redirects,
            timeout=self.config.timeout,
        )
        return CurlResponse(response)

    def put(
        self,
        url: str,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        follow_redirects: bool = True,
    ) -> AbstractResponse:
        self._check_context_manager()
        session = self._get_session()
        response = session.put(
            url,
            json=data,
            headers=headers,
            allow_redirects=follow_redirects,
            timeout=self.config.timeout,
        )
        return CurlResponse(response)

    def delete(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        follow_redirects: bool = True,
    ) -> AbstractResponse:
        self._check_context_manager()
        session = self._get_session()
        response = session.delete(
            url,
            headers=headers,
            allow_redirects=follow_redirects,
            timeout=self.config.timeout,
        )
        return CurlResponse(response)

    async def aget(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        follow_redirects: bool = True,
    ) -> AbstractResponse:
        self._check_context_manager()
        session = await self._get_async_session()
        response = await session.get(
            url,
            params=params,
            headers=headers,
            allow_redirects=follow_redirects,
            timeout=self.config.timeout,
        )
        return CurlResponse(response)

    async def apost(
        self,
        url: str,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        follow_redirects: bool = True,
    ) -> AbstractResponse:
        self._check_context_manager()
        session = await self._get_async_session()
        response = await session.post(
            url,
            json=data,
            headers=headers,
            allow_redirects=follow_redirects,
            timeout=self.config.timeout,
        )
        return CurlResponse(response)

    async def aput(
        self,
        url: str,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        follow_redirects: bool = True,
    ) -> AbstractResponse:
        self._check_context_manager()
        session = await self._get_async_session()
        response = await session.put(
            url,
            json=data,
            headers=headers,
            allow_redirects=follow_redirects,
            timeout=self.config.timeout,
        )
        return CurlResponse(response)

    async def adelete(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        follow_redirects: bool = True,
    ) -> AbstractResponse:
        self._check_context_manager()
        session = await self._get_async_session()
        response = await session.delete(
            url,
            headers=headers,
            allow_redirects=follow_redirects,
            timeout=self.config.timeout,
        )
        return CurlResponse(response)
