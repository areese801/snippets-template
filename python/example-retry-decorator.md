---
id: 00000000-0000-0000-0000-000000000002
title: "Retry Decorator with Exponential Backoff"
language: "python"
tags: [decorator, retry, error-handling, example]
description: "Decorator that retries a function with exponential backoff - demonstrates snippet format"
created: "2026-03-06"
last_updated: "2026-03-06"
---

import time
from functools import wraps

def retry(max_attempts=3, base_delay=1):
    """Retry decorator with exponential backoff."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_attempts - 1:
                        raise
                    delay = base_delay * (2 ** attempt)
                    time.sleep(delay)
        return wrapper
    return decorator

# Usage:
# @retry(max_attempts=3, base_delay=1)
# def flaky_api_call():
#     ...
