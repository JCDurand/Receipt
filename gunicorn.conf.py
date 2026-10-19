"""
Gunicorn serves Django inside the Docker network; Nginx is the public server in
front of it. Started by entrypoint.sh when DJANGO_DEBUG is not 1.
"""
import os

bind = "0.0.0.0:8000"

# Threaded workers: requests mostly wait on the database or on a parser, and an
# upload being read must not hold up everyone else on the same worker.
worker_class = "gthread"
workers = int(os.environ.get("WEB_CONCURRENCY", "3"))
threads = int(os.environ.get("GUNICORN_THREADS", "4"))

# A worker that stops responding for this long is killed and replaced. It is
# also how long a worker that is shutting down has to finish a document it is
# still parsing in the background.
timeout = 95

# On SIGTERM (docker stop, a deploy) workers stop taking requests and get this
# long to finish the ones in progress. Keep stop_grace_period above it.
graceful_timeout = 30

keepalive = 5

# The heartbeat file goes in memory, as the container's disk can stall it
worker_tmp_dir = "/dev/shm"

# Nginx is the only client, so its X-Forwarded-* headers can be trusted
forwarded_allow_ips = "*"

# Logs go to the container's output, alongside Django's
accesslog = "-"
errorlog = "-"
