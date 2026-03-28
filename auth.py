import webbrowser
from wsgiref import simple_server
from urllib.parse import parse_qs
import threading
import secrets
import hashlib
import base64
import requests
import string
import time
import json


def challenge():
    verifier = "".join(
        secrets.choice(string.ascii_letters + string.digits) for _ in range(128)
    )
    hashed = hashlib.sha256(verifier.encode()).digest()
    code_challenge = base64.urlsafe_b64encode(hashed).decode().replace("=", "")
    return verifier, code_challenge


# def authorize(settings: dict):
def authorize():
    response = {}
    callback_done = threading.Event()

    def callback(environ, start_response):
        start_response("200 OK", [("Content-Type", "text/html")])
        response.update(parse_qs(environ["QUERY_STRING"]))
        callback_done.set()
        return [b"Authorization complete. You can close this window."]

    client_id = "c89ab668d1b04069b03b793c940bd5b4"
    state = "".join(
        secrets.choice(string.ascii_lowercase + string.digits) for _ in range(16)
    )
    verifier, code_challenge = challenge()
    scopes = ["playlist-modify-public", "playlist-modify-private"]
    redirect_uri = "http://127.0.0.1:8888/callback"
    url = f"https://accounts.spotify.com/authorize?client_id={client_id}&response_type=code&code_challenge_method=S256&code_challenge={code_challenge}&redirect_uri={redirect_uri}&state={state}&scope={"%20".join(scopes)}"
    webbrowser.open(url)
    server_ip = redirect_uri.split("//")[1].split(":")[0]
    server_port = int(redirect_uri.split("//")[1].split(":")[1].split("/")[0])
    server = simple_server.make_server(server_ip, server_port, callback)
    timeout = 240  # 4 minute timeout period
    server.timeout = timeout
    server_thread = threading.Thread(target=server.handle_request)
    server_thread.start()
    if not callback_done.wait(timeout=timeout):
        server_thread.join()
        raise Exception("Connection timeout")
    server_thread.join()
    if response["state"][0] != state:
        raise Exception("Error: State mismatch")
    if "error" in response:
        raise Exception("Error: " + response["error"][0])
    code = response["code"][0]
    url = "https://accounts.spotify.com/api/token"
    payload = {
        "client_id": client_id,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "code_verifier": verifier,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    response = requests.post(
        "https://accounts.spotify.com/api/token", data=payload, headers=headers
    )
    response.raise_for_status()
    # settings['authorization_token'] = code
    # settings['refresh_token'] = json.loads(response.text)['refresh_token']
    # with open('settings.json', 'w') as f:
    #     f.write(json.dumps(settings, indent=2))
    return json.loads(response.text)
    return json.loads(response.text)["access_token"]
    # return response['code'][0]
    # print(response['code'][0])


if __name__ == "__main__":
    # import json
    # with open('settings.json', 'r') as f:
    # settings = json.loads(f.read())
    print(authorize())
