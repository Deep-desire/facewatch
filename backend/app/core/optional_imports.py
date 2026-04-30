from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io


def safe_import_cv2():
    """Import OpenCV without leaking its noisy NumPy compatibility traceback."""
    stdout = io.StringIO()
    stderr = io.StringIO()
    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            import cv2  # type: ignore
        return cv2, True, None
    except Exception as exc:
        return None, False, exc
