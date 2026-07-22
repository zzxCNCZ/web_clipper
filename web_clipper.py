"""Compatibility exports for integrations using the legacy module."""

import uvicorn

from app import create_app
from app.services import WebClipperService, parse_filename

app = create_app()


def start_server(host: str = "0.0.0.0", port: int = 65330) -> None:
    uvicorn.run(app, host=host, port=port)


WebClipperHandler = WebClipperService

__all__ = [
    "WebClipperHandler",
    "WebClipperService",
    "app",
    "parse_filename",
    "start_server",
]
