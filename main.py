from web_clipper import start_server
from config import CONFIG

if __name__ == "__main__":
    start_server(
        host=CONFIG.get('host', '0.0.0.0'),
        port=CONFIG.get('port', 8000)
    ) 