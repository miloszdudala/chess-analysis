#!/bin/bash
# Double-click this in Finder to start the app and open it in the browser.
# It runs through Terminal, which already has permission to read this folder —
# handy if the Dock app is still waiting on its Documents-access prompt.
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/bin/chess-analyzer"
