from typing import Protocol
from uuid import UUID


class PublicationNotifier(Protocol):
    def published(self, run_id: UUID, status: str) -> None: ...


class NoOpNotifier:
    def published(self, run_id: UUID, status: str) -> None:
        return None
