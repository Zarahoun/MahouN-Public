#!/usr/bin/env python3
"""
Integrity Probe
===============
Hardened Healthcheck for MAHOUN Backend
Verifies active connections to Neo4j and Redis.
Strict-Mode Enforcement: Returns exit code 1 if unavailable, forcing a 503 on the API level.
"""

import os
import sys
import logging

# Configure minimal logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("IntegrityProbe")


def check_redis():
    """Verify Redis connection"""
    try:
        import redis

        # Fetch Redis connection details from ENV
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        client = redis.Redis.from_url(
            redis_url, socket_connect_timeout=3, socket_timeout=3
        )
        client.ping()
        logger.info("Redis connection verified.")
        return True
    except ImportError:
        logger.error("Redis module not installed.")
        return False
    except Exception as e:
        logger.error(f"Redis connection failed: {e}")
        return False


def check_neo4j():
    """Verify Neo4j connection"""
    try:
        from mahoun.graph.neo4j.connection import get_connection
        conn = get_connection()
        result = conn.ping()
        if result:
            logger.info("Neo4j connection verified.")
        else:
            logger.error("Neo4j ping returned False.")
        return result
    except ImportError:
        logger.error("Neo4j connection module not available.")
        return False
    except Exception as e:
        logger.error(f"Neo4j connection failed: {e}")
        return False


def main():
    guard_mode = os.getenv("MAHOUN_GUARD_MODE", "STRICT")
    logger.info(f"Starting Integrity Probe [Mode: {guard_mode}]")

    neo4j_ok = check_neo4j()
    redis_ok = check_redis()

    if not (neo4j_ok and redis_ok):
        logger.error("CRITICAL: Sources of Truth are unreachable.")
        if guard_mode == "STRICT":
            logger.error(
                "STRICT MODE ENFORCED. Container marked Unhealthy (503 Trigger)."
            )
            sys.exit(1)
        else:
            logger.warning("Guard mode is not STRICT, but allowing degradation.")
            # For strict compliance according to docs context, we exit 1 anyway if neo4j drops
            sys.exit(1)

    logger.info("All systems nominal. Container Healthy.")
    sys.exit(0)


if __name__ == "__main__":
    main()
