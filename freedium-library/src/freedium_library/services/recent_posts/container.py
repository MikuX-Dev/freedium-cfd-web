from dependency_injector import containers, providers

from .service import RecentPostsService


class RecentPostsContainer(containers.DeclarativeContainer):
    service = providers.Singleton(RecentPostsService)
