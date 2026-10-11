from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ModelRequest:
    operation: str
    capability: str
    prompt: str
    inputs: list[dict[str, Any]]
    parameters: dict[str, Any]
    output_kind: str
    request_id: str


@dataclass
class ModelOutput:
    url: str = ''
    base64: str = ''
    mime: str = 'image/png'


@dataclass
class ModelResult:
    status: str
    outputs: list[ModelOutput] = field(default_factory=list)
    remote_id: str = ''
    error: str = ''


class ModelAdapter(ABC):
    def __init__(self, provider):
        self.provider = provider

    @abstractmethod
    def submit(self, request: ModelRequest) -> ModelResult:
        """Submit once. Request ID may be mapped to vendor idempotency headers."""

    @abstractmethod
    def poll(self, remote_id: str) -> ModelResult:
        """Query an existing task; never submit another paid request."""
