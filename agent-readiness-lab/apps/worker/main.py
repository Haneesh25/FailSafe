"""Worker main entry point."""

import os
import sys

# Add packages to path before other imports
sys.path.insert(0, "/app/packages")
sys.path.insert(0, "/app/apps/worker")

from redis import Redis
from rq import Worker, Queue, Connection

# Import tasks module to register with RQ
import tasks  # noqa: F401


def get_redis_url() -> str:
    """Get Redis URL from environment."""
    return os.environ.get("REDIS_URL", "redis://redis:6379/0")


def main():
    """Start the worker."""
    redis_conn = Redis.from_url(get_redis_url())

    with Connection(redis_conn):
        worker = Worker(["default"])
        worker.work()


if __name__ == "__main__":
    main()
