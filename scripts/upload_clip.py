import argparse
from pathlib import Path

import requests


def upload_html(file_path: Path, server_url: str, api_key: str, original_url: str = "") -> dict:
    if not file_path.is_file():
        raise FileNotFoundError(f"文件未找到: {file_path}")

    headers = {"Authorization": f"Bearer {api_key}"}
    with file_path.open("rb") as file:
        response = requests.post(
            server_url,
            headers=headers,
            files={"singlehtmlfile": (file_path.name, file, "text/html")},
            data={"url": original_url},
            timeout=300,
        )
    response.raise_for_status()
    return response.json()


def main() -> None:
    parser = argparse.ArgumentParser(description="上传 HTML 文件到 Web Clipper")
    parser.add_argument("file", type=Path, help="要上传的 HTML 文件路径")
    parser.add_argument("--url", default="http://127.0.0.1:65330/upload", help="服务端 URL")
    parser.add_argument("--source-url", default="", help="网页原始 URL")
    parser.add_argument("--key", required=True, help="API Bearer Token")
    args = parser.parse_args()

    result = upload_html(args.file, args.url, args.key, args.source_url)
    print(f"GitHub URL: {result['github_url']}")
    print(f"Notion URL: {result['notion_url']}")


if __name__ == "__main__":
    main()
