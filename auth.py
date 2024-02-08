import webbrowser
from wsgiref import simple_server
from urllib.parse import parse_qs
from threading import Thread
import secrets
import hashlib
import base64
import requests
import string
import time

response = {}

def challenge():
    verifier = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(128))
    hashed = hashlib.sha256(verifier.encode()).digest()
    code_challenge = base64.urlsafe_b64encode(hashed).decode().replace('=', '')
    return verifier, code_challenge

def callback(environ, start_response):
    start_response('200 OK', [('Content-Type', 'text/html')])
    global response
    response = parse_qs(environ['QUERY_STRING'])
    return ''

def authorize(settings: dict):
    global response
    client_id = 'c89ab668d1b04069b03b793c940bd5b4'
    state = ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(16))
    verifier, code_challenge = challenge()
    url = f'https://accounts.spotify.com/authorize?client_id={client_id}&response_type=code&code_challenge_method=S256&code_challenge={code_challenge}&redirect_uri=http://localhost:8080/callback&state={state}'#&scope=playlist-modify-public%20playlist-modify-private'
    webbrowser.open(url)
    server = simple_server.make_server('localhost', 8080, callback)
    server_thread = Thread(target=server.serve_forever)
    server_thread.start()
    timeout = time.time() + 60
    while True:
        if time.time() > timeout:
            server.shutdown()
            server_thread.join()
            raise Exception('Connection timeout')
        if response:
            server.shutdown()
            server_thread.join()
            break
    if response['state'][0] != state:
        raise Exception('Error: State mismatch')
    if 'error' in response:
        raise Exception('Error: ' + response['error'][0])
    code = response['code'][0]
    url = 'https://accounts.spotify.com/api/token'
    payload = {
        'client_id': client_id,
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': 'http://localhost:8080/callback',
        'code_verifier': verifier
    }
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    response = requests.post('https://accounts.spotify.com/api/token', data=payload, headers=headers)
    settings['authorization_token'] = code
    settings['refresh_token'] = json.loads(response.text)['refresh_token']
    with open('settings.json', 'w') as f:
        f.write(json.dumps(settings, indent=2))
    return json.loads(response.text)['access_token']
    # return response['code'][0]
    # print(response['code'][0])

if __name__ == '__main__':
    import json
    with open('settings.json', 'r') as f:
        settings = json.loads(f.read())
    authorize(settings)