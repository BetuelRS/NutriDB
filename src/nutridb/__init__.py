"""Version information for nutridb."""

from importlib.metadata import PackageNotFoundError, version

__all__ = ["__version__"]

try:
    __version__ = version("nutridb")
except PackageNotFoundError:  # pragma: no cover - editable/plain checkout
    __version__ = "0.0.0.dev0"
