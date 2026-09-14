try:
    import importlib.metadata as importlib_metadata
except ModuleNotFoundError:
    import importlib_metadata

try:
    __version__ = importlib_metadata.version(__package__ or __name__)
except Exception:
    # If package metadata is not available (e.g., when not installed via pip)
    __version__ = "unknown"
