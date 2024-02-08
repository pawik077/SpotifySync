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
		return self.uri == o.uri
	def __ne__(self, o: object) -> bool:
		return self.uri != o.uri

def refresh() -> str:
	url = "https://accounts.spotify.com/api/token"
	payload = 'grant_type=refresh_token&refresh_token=' + settings['refresh_token']
	headers = {
		'Authorization': 'Basic ' + settings['authorization_token'],
		'Content-Type': 'application/x-www-form-urlencoded'
	}
	try:
		response = requests.post(url, headers=headers, data=payload)
		response.raise_for_status()
	except requests.exceptions.ConnectionError:
		sys.stderr.write(
			f'{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}: Error while getting authorization key - Server connection error\n')
		sys.exit(-10)
	except requests.exceptions.HTTPError as status:
		sys.stderr.write(f'{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}: Error while getting authorization key - Server response: {status}\n')
		sys.exit(-1)
	return json.loads(response.text)['access_token']

def getPlaylist(playlistId: str, authKey: str) -> Track:
	playlist = []
	url = 'https://api.spotify.com/v1/playlists/' + playlistId + '/tracks'
	headers = {
		'Authorization': authKey
	}
	while url != None:
		response = requests.get(url, headers=headers)
		try:
			response.raise_for_status()
		except requests.exceptions.HTTPError as status:
			sys.stderr.write(f'{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}: Error while downloading playlist contents - Server response: {status}\n')
			sys.exit(-2)
		for item in json.loads(response.text)['items']:
			track = Track(item['track']['name'], '', item['track']['uri'])
			artists = len(item['track']['artists'])
			for artist in item['track']['artists']:
				track.artist += artist['name']
				artists -= 1
				if artists != 0:
					track.artist += ', '
			playlist.append(track)
		url = json.loads(response.text)['next']
	return playlist

def addToPlaylist(playlistId: str, uri: str, pos: int, authKey: str) -> requests.models.Response:
	url = 'https://api.spotify.com/v1/playlists/' + playlistId + '/tracks?uris=' + uri + '&position=' + str(pos)
	headers = {
		'Authorization': authKey
	}
	response = requests.post(url, headers=headers)
	return response

def removeFromPlaylist(playlistId: str, uri: str, authKey: str) -> requests.models.Response:
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
	response = requests.delete(url, headers=headers, data=payload)
	return response

def reorderPlaylist(playlistId: str, initPos: int, endPos: int, authKey: str) -> requests.models.Response:
	url = 'https://api.spotify.com/v1/playlists/' + playlistId + '/tracks'
	headers = {
		'Authorization': authKey,
		'Content-Type': 'application/json'
	}
	payload = '{\
		"range_start": ' + str(initPos) + ',\
		"insert_before": ' + str(endPos) + '\
	}'
	response = requests.put(url, headers=headers, data=payload)
	return response
try:
	with open('settings.json', 'r') as s:
		settings = json.load(s)
except FileNotFoundError:
	sys.stderr.write(f'{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}: Error while reading settings file - settings.json file not found\n')
	sys.exit(-2)
