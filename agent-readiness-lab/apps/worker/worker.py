"""Worker module - RQ worker entry point with task imports."""

import os
import sys

# Add packages to path
sys.path.insert(0, "/app/packages")

# Import tasks to make them available to RQ
from tasks import run_evaluation

__all__ = ["run_evaluation"]
