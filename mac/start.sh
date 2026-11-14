#!/bin/sh
# Starts the script that draws the Kindle screen and sends it to the address in
# kindle.json. With "local" it also runs the server on this Mac, for use
# without Home Assistant (set "addon" to http://127.0.0.1:4796 and point the
# Kindle's server.txt at this Mac). Stop with: mac/start.sh stop
cd "$(dirname "$0")/.."
pkill -f "quiet/server.py" 2>/dev/null
pkill -f "mac/kindle.py" 2>/dev/null
[ "$1" = "stop" ] && { echo "stopped"; exit 0; }
if [ "$1" = "local" ]; then
  nohup /usr/bin/python3 quiet/server.py > /tmp/quiet-server.log 2>&1 &
  sleep 1
fi
nohup /usr/bin/python3 mac/kindle.py > /tmp/quiet-kindle.log 2>&1 &
echo "running; log in /tmp/quiet-kindle.log"
