"""Core shared type stubs."""

from typing import TypedDict


class PromptLookup(TypedDict, total=False):
    name: str
    status: str
    body: str


class SharedMetadata(TypedDict, total=False):
    version: str
    source: str
