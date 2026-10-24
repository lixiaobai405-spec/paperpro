"""Serialize PyMuPDF access inside one ASGI worker (it is not thread-safe)."""
from functools import wraps
from threading import RLock


PDF_LOCK = RLock()


def serialized_pdf(function):
    @wraps(function)
    def guarded(*args, **kwargs):
        with PDF_LOCK:
            return function(*args, **kwargs)
    return guarded
