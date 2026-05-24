from dependency_injector import containers, providers

from freedium_library.services.medium.validators import (
    MediumServicePathValidator,
)
from freedium_library.utils.http import CurlRequest

from .api import MediumApiService
from .config import MediumConfig
from .medium import MediumService


class MediumContainer(containers.DeclarativeContainer):
    config = providers.Singleton(MediumConfig)
    request = providers.Singleton(CurlRequest)

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
