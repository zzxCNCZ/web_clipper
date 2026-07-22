from pydantic import BaseModel


class ClipResponse(BaseModel):
    status: str
    github_url: str
    notion_url: str


class HealthResponse(BaseModel):
    status: str
    configured: bool
