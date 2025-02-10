import requests
import os
from pathlib import Path
import argparse
import sys

def upload_html(
    file_path, 
    server_url="http://example.com/upload/",  # 根据实际端口修改
    api_key="your-token-here"  # 使用配置文件中设置的 api_key
):
    """上传 HTML 文件到服务器
    
    Args:
        file_path: HTML 文件路径
        server_url: 服务器 URL
        api_key: API 密钥
    """
    headers = {
        "Authorization": f"Bearer {api_key}"  # 使用 Bearer 认证
    }
    
    # 确保文件存在
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"文件未找到: {file_path}")
    
    # 准备文件
    with open(file_path, 'rb') as f:
        files = {'file': (Path(file_path).name, f, 'text/html')}
        
        try:
            print(f"正在上传文件: {file_path}")
            response = requests.post(
                server_url, 
                headers=headers, 
                files=files
            )
            
            # 检查响应状态
            response.raise_for_status()
            
            result = response.json()
            print("上传成功！")
            print(f"GitHub URL: {result['github_url']}")
            print(f"Notion URL: {result['notion_url']}")
            return result
            
        except requests.exceptions.RequestException as e:
            if hasattr(e.response, 'text'):
                print(f"服务器响应: {e.response.text}")
            raise Exception(f"上传失败: {str(e)}")

def main():
    # 创建命令行参数解析器
    parser = argparse.ArgumentParser(description='上传 HTML 文件到 Web Clipper 服务器')
    parser.add_argument('file', help='要上传的 HTML 文件路径')
    parser.add_argument('--url', 
                       default="http://example.com/upload/",
                       help='服务器 URL (默认: http://example.com/upload/)')
    parser.add_argument('--key', 
                       default="your-token-here",
                       help='API 密钥')

    # 解析命令行参数
    args = parser.parse_args()

    try:
        # 上传文件
        upload_html(
            args.file,
            server_url=args.url,
            api_key=args.key
        )
    except Exception as e:
        print(f"错误: {str(e)}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
