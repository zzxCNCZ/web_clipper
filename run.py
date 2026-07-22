import uvicorn

from app import create_app
from app.config import Settings

settings = Settings.from_env()
app = create_app(settings)


if __name__ == "__main__":
    uvicorn.run("run:app", host=settings.host, port=settings.port, reload=False)
