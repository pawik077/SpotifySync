import webbrowser
from wsgiref import simple_server
from urllib.parse import parse_qs
from threading import Thread
import random
import string
import time

response = {}

def callback(environ, start_response):
    start_response('200 OK', [('Content-Type', 'text/html')])
    global response
    response = parse_qs(environ['QUERY_STRING'])
    return ''

def auth():
    client_id = 'c89ab668d1b04069b03b793c940bd5b4'
    state = ''.join(random.choices(string.ascii_lowercase + string.digits, k=16))
    url = f'https://accounts.spotify.com/authorize?client_id={client_id}&response_type=code&redirect_uri=http://localhost:8080/callback&state={state}'#&scope=playlist-modify-public%20playlist-modify-private'
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
    return response['code'][0]
    # print(response['code'][0])

if __name__ == '__main__':
    auth()