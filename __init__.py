from __future__ import annotations


def __getattr__(name: str):
    if name == "AnimePlugin":
        from .main import AnimePlugin

        return AnimePlugin
    raise AttributeError(name)


__all__ = ["AnimePlugin"]
