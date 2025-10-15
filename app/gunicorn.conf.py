import multiprocessing
import os

bind = '0.0.0.0:8000'
workers = multiprocessing.cpu_count() * 2 + 1
timeout = int(os.environ.get("SCAN_UPLOAD_TIMEOUT_SECONDS", "60"))
