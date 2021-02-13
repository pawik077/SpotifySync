import json
import requests

class Track:
  def __init__(self, title: str = '', artist: str = '', uri: str = '') -> None:
    self.artist = artist
    self.title = title
    self.uri = uri
  def __eq__(self, o: object) -> bool:
      if self.uri == o.uri:
        return True
      else:
        return False
  def __ne__(self, o: object) -> bool:
      if self.uri != o.uri:
        return True
      else:
        return False

def authorize() -> str:
  url = "https://accounts.spotify.com/api/token"
  payload = 'grant_type=refresh_token&refresh_token=' + settings['refresh_token']
  headers = {
    'Authorization': 'Basic ' + settings['authorization_token'],
    'Content-Type': 'application/x-www-form-urlencoded'
  }
  response = requests.request('POST', url, headers=headers, data=payload)
  return json.loads(response.text)['access_token']

def addToPlaylist(playlistId: str, uri: str, pos: int) -> requests.models.Response:
  url = 'https://api.spotify.com/v1/playlists/' + playlistId + '/tracks?uris=' + uri + '&position=' + str(pos)
  headers = {
    'Authorization': authKey
  }
  response = requests.request('POST', url, headers=headers)
  return response

def removeFromPlaylist(playlistId: str, uri: str) -> requests.models.Response:
  url = 'https://api.spotify.com/v1/playlists/' + playlistId + '/tracks'
  headers = {
      'Authorization': authKey
  }
  payload = '{\
    "tracks": [\
        {\
            "uri": "' + uri + '"\
        }\
    ]\
  }'
  response = requests.request('DELETE', url, headers=headers, data=payload)
  return response

def reorderPlaylist(playlistId: str, initPos: int, endPos: int) -> requests.models.Response:
  url = 'https://api.spotify.com/v1/playlists/' + playlistId + '/tracks'
  headers = {
      'Authorization': authKey,
      'Content-Type': 'application/json'
  }
  payload = '{\
    "range_start": ' + str(initPos) + ',\
    "insert_before": ' + str(endPos) + '\
    }'
  print(payload)
  response = requests.request('PUT', url, headers=headers, data=payload)
  return response

settings = json.load(open('settings.json', 'r'))
authKey = 'Bearer ' + authorize()
