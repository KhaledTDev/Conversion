# gunicorn_config.py
import multiprocessing

workers = 2  # Empezar con menos workers
worker_class = "uvicorn.workers.UvicornWorker"
timeout = 7200
keepalive = 60
bind = "0.0.0.0:8000"
log_level = "info"
accesslog = "access.log"
errorlog = "error.log"
max_requests = 1000
max_requests_jitter = 50