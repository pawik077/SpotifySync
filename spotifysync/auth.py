import webbrowser
from wsgiref import simple_server
import urllib.parse
import threading
import secrets
import hashlib
import base64
import requests
import string
from queue import Queue, Empty


def challenge() -> tuple[str, str]:
    verifier = "".join(
        secrets.choice(string.ascii_letters + string.digits) for _ in range(128)
    )
    hashed = hashlib.sha256(verifier.encode()).digest()
    code_challenge = base64.urlsafe_b64encode(hashed).decode().replace("=", "")
    return verifier, code_challenge


def authorize(client_id: str) -> tuple[str, str, int]:
    callback_queue = Queue()

    def callback(environ, start_response) -> list[bytes]:
        if environ.get("PATH_INFO") != "/callback":
            start_response("404 Not Found", [])
            return [b""]
        start_response("200 OK", [("Content-Type", "text/html")])
        callback_queue.put(urllib.parse.parse_qs(environ["QUERY_STRING"]))
        return [b"""<html><body>
            <p>Authorization complete. You can close this window.</p>
            <script>window.close();</script>
        </body></html>"""]

    state = "".join(
        secrets.choice(string.ascii_lowercase + string.digits) for _ in range(16)
    )
    verifier, code_challenge = challenge()
    scopes = [
        "playlist-modify-public",
        "playlist-modify-private",
        "playlist-read-private",
    ]
    redirect_uri = "http://127.0.0.1:8888/callback"
    params = {
        "client_id": client_id,
        "response_type": "code",
        "code_challenge_method": "S256",
        "code_challenge": code_challenge,
        "redirect_uri": redirect_uri,
        "state": state,
        "scope": " ".join(scopes),
    }
    url = "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode(params)
    redirect_uri_parsed = urllib.parse.urlparse(redirect_uri)
    server_ip = redirect_uri_parsed.hostname
    server_port = redirect_uri_parsed.port
    if server_port is None:
        server_port = 80
    assert server_ip is not None
    server = simple_server.make_server(server_ip, server_port, callback)
    timeout = 240  # 4 minute timeout period
    server.timeout = timeout
    server_thread = threading.Thread(target=server.handle_request)
    server_thread.start()
    webbrowser.open(url)
    try:
        callback_response = callback_queue.get(timeout=timeout)
    except Empty:
        server_thread.join()
        raise TimeoutError("Connection timeout")
    server_thread.join()
    try:
        if callback_response["state"][0] != state:
            raise ValueError("Error: State mismatch")
        if "error" in callback_response:
            raise ValueError("Error: " + callback_response["error"][0])
        code = callback_response["code"][0]
    except KeyError:
        raise KeyError("Error: Malformed request response")
    token_url = "https://accounts.spotify.com/api/token"
    payload = {
        "client_id": client_id,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "code_verifier": verifier,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    response = requests.post(
        token_url,
        data=payload,
        headers=headers,
    )
    response.raise_for_status()
    data = response.json()
    return data["access_token"], data["refresh_token"], data["expires_in"]
