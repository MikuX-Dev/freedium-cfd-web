from dependency_injector import containers, providers

from freedium_library.api.config import APIConfig, ImageProxyConfig, ServerConfig


class APIContainer(containers.DeclarativeContainer):
    config = providers.Singleton(APIConfig)
    server_config = providers.Singleton(ServerConfig)
    image_proxy_config = providers.Singleton(ImageProxyConfig)
