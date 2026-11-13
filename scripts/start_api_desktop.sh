#!/bin/bash
# Desktop mode startup script - disables Neo4j and Redis requirements

# Set environment variables for desktop minimal mode
export MAHOUN_MODE=desktop_minimal
export MAHOUN_GRAPH_ENABLED=false
export MAHOUN_ENABLE_NEO4J=false
export MAHOUN_ENABLE_REDIS=false
export MAHOUN_ENABLE_POSTGRES=true

# Activate virtual environment
source venv/bin/activate

# Run the API
python -m api.main