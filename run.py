import sys
from spotifysync import gui, sync

if len(sys.argv) > 1 and sys.argv[1] == "--sync":
    sync.main()
else:
    gui.main()
