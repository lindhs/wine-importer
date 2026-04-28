from .pipeline import run_pipeline

__all__ = ["run_pipeline"]

try:
    from .cli import app
except ModuleNotFoundError:
    app = None
else:
    __all__.append("app")
