"""
Gunicorn production config.
Adjust workers/threads based on your server's CPU count.
Rule of thumb: workers = (2 x CPU cores) + 1
"""
import multiprocessing
import os

# ── Binding ───────────────────────────────────────────────────────────────────
port    = os.environ.get('PORT', '5000')
bind    = f'0.0.0.0:{port}'
workers = multiprocessing.cpu_count() * 2 + 1

# ── Worker class ──────────────────────────────────────────────────────────────
worker_class    = 'sync'
worker_connections = 1000
threads         = 2
timeout         = 120          # seconds — long enough for Groq AI calls
keepalive       = 5

# ── Logging ───────────────────────────────────────────────────────────────────
accesslog  = '-'               # stdout
errorlog   = '-'               # stderr
loglevel   = 'info'

# ── Process naming ────────────────────────────────────────────────────────────
proc_name = 'disaster-response'

# ── Security ──────────────────────────────────────────────────────────────────
limit_request_line       = 4096
limit_request_fields     = 100
limit_request_field_size = 8192
