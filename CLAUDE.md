# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## High-Level Architecture

- **Main Entry Point:**
  - The server is started via `main.py`, which initializes a FastAPI application using configurations in `config.py`.

- **Core Application (`web_clipper.py`):**
  - This houses the primary logic for web clipping, including the FastAPI app definition, route handling, file uploads, API interactions with external services like GitHub, Notion, and Telegram, and use of OpenAI's API for generating content summaries and tags.

- **Configuration:**
  - Managed in `config.py`, which includes settings like API keys and content limits.

- **Dependencies:**
  - Listed in `requirements.txt`, likely including FastAPI and API clients.

- **Containerization:**
  - `Dockerfile` and `docker-compose.yml` are provided for deployment.

## Development Commands

- **Running the Service:**
  ```bash
  python main.py
  ```
  - Starts the FastAPI server.

- **API Request Example:**
  ```bash
  curl -X POST "http://your-instance-url/upload" \
       -H "Authorization: Bearer your-api-key" \
       -F "singlehtmlfile=@webpage.html" \
       -F "url=https://original-url.com"
  ```