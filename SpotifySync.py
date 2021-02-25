import json
import requests
import sys
import datetime

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
  try:
    response.raise_for_status()
  except requests.exceptions.HTTPError as status:
    sys.stderr.write(f'=== {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")} ===\n')
    sys.stderr.write('An error occured while getting authorization key!!\n')
    sys.stderr.write(f'Server response: {status}\n')
    sys.exit(-1)
  return json.loads(response.text)['access_token']

def getPlaylist(playlistId: str) -> Track:
  playlist = []
  url = 'https://api.spotify.com/v1/playlists/' + playlistId + '/tracks'
  headers = {
      'Authorization': authKey
  }
  while url != None:
    response = json.loads(requests.request('GET', url, headers=headers).text)
    for item in response['items']:
      track = Track(item['track']['name'], '', item['track']['uri'])
      artists = len(item['track']['artists'])
      for artist in item['track']['artists']:
        track.artist += artist['name']
        artists -= 1
        if artists != 0:
          track.artist += ', '
      playlist.append(track)
    url = response['next']
  return playlist

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
  response = requests.request('PUT', url, headers=headers, data=payload)
  return response

settings = json.load(open('settings.json', 'r'))
authKey = 'Bearer ' + authorize()

playlists = []

mergedPlaylist = getPlaylist(settings['merge_playlist'])
for playlist in settings['playlists']:
  playlists.append((playlist['name'], getPlaylist(playlist['id'])))

for track in mergedPlaylist:
  found = False
  for playlist in playlists:
    if track in playlist[1]:
      found = True
  if found == False:
    removeFromPlaylist(settings['merge_playlist'], track.uri)
    mergedPlaylist.remove(track)
    print(f'Removed {track.title} by {track.artist} from merged playlist')

index = 0
for playlist in playlists:
  for track in playlist[1]:
    if track not in mergedPlaylist:
      addToPlaylist(settings['merge_playlist'], track.uri, index + playlist[1].index(track))
      mergedPlaylist.insert(index + playlist[1].index(track), track)
      print(f'Added {track.title} by {track.artist} from {playlist[0]} to merged playlist')
    if mergedPlaylist.index(track) != index + playlist[1].index(track):
      reorderPlaylist(settings['merge_playlist'], mergedPlaylist.index(track), index + playlist[1].index(track))
      oldIndex = mergedPlaylist.index(track)
      mergedPlaylist.remove(track)
      mergedPlaylist.insert(index + playlist[1].index(track), track)
      print(f'Moved {track.title} by {track.artist} from position {oldIndex} to {mergedPlaylist.index(track)}')
  index += len(playlist[1])
