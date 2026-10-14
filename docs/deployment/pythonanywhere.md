# PythonAnywhere cache configuration

The taxonomy sync preview is shared between web workers through Django’s cache. PythonAnywhere deployments without Redis should use the file-based cache:

```python
os.environ["CACHE_BACKEND"] = "file"
```

Set this in the WSGI file before `get_wsgi_application()` is called, then reload the web app. The default cache directory is `.cache` under the application base directory; set `CACHE_LOCATION` if a different shared writable directory is preferred.

If an external Redis service is available, use this instead:

```python
os.environ["USE_REDIS"] = "true"
os.environ["REDIS_URL"] = "rediss://:password@example-host:6380/0"
```
