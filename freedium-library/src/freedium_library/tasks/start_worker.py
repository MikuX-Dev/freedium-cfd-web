#!/usr/bin/env python3
"""Worker entrypoint: start the Prometheus metrics sidecar, then exec the
TaskIQ worker. The sidecar runs in a daemon thread so it exits cleanly when
the TaskIQ process terminates."""

from freedium_library.tasks.metrics_server import start_metrics_server

# Must start BEFORE any prometheus_client metrics are imported (they switch
# to multiprocess mode on import if PROMETHEUS_MULTIPROC_DIR is set).
start_metrics_server()

# Let the sidecar bind before spawning TaskIQ child processes.
import time
time.sleep(0.1)

import os
import sys

# exec the TaskIQ worker — replaces this Python process so we don't
# waste memory on a parent that does nothing.
os.execvp("taskiq", ["taskiq", "worker", "freedium_library.tasks:broker"] + sys.argv[1:])
