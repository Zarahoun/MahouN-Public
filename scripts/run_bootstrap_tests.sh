#!/bin/bash
# Bootstrap integration test runner
export MAHOUN_INTEGRATION=1
export MAHOUN_ENV=test
export MAHOUN_TESTING=1
export ENABLE_POSTGRES=false
export ENABLE_NEO4J=false
export ENABLE_REDIS=false
export MAHOUN_GRAPH_BACKEND=disabled_fallback
export NEO4J_PASSWORD=testpass

cd /home/haji/Desktop/KingMahouN
/home/haji/Desktop/KingMahouN/venv/bin/python -m pytest "$@"
