"""Backward-compatible entry point; prefer ``python run.py``."""

from run import app, settings

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.host, port=settings.port)
