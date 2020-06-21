import sys
from webserver import webserver

if len(sys.argv) > 1:
    webserver.start(int(sys.argv[1]))
else:
    webserver.start()
