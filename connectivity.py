import socket
from urllib.parse import urlparse

from config import BASE_URL


def is_online(url=BASE_URL, timeout=3):
    parsed_url = urlparse(url)
    host = parsed_url.hostname
    port = 443 if parsed_url.scheme == "https" else 80

    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False
