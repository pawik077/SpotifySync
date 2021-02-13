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
