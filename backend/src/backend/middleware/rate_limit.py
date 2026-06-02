"""
Rate limiting middleware for Flask API
Prevents abuse by limiting the number of requests per IP address
"""
import time
from collections import defaultdict
from functools import wraps
from typing import Callable, Dict, Tuple

import structlog
from flask import request, jsonify

log = structlog.get_logger()

# Store request counts: {ip_address: [(timestamp, count), ...]}
_request_store: Dict[str, list[Tuple[float, int]]] = defaultdict(list)

# Configuration
DEFAULT_RATE_LIMIT = 100  # requests
DEFAULT_WINDOW = 60  # seconds


def get_client_ip() -> str:
    """
    Get the client's IP address from the request
    Handles proxies and load balancers
    """
    # Check for X-Forwarded-For header (common with proxies)
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    
    # Check for X-Real-IP header
    if request.headers.get('X-Real-IP'):
        return request.headers.get('X-Real-IP')
    
    # Fall back to remote_addr
    return request.remote_addr or 'unknown'


def clean_old_requests(ip: str, window: int) -> None:
    """Remove requests older than the time window"""
    current_time = time.time()
    cutoff_time = current_time - window
    
    if ip in _request_store:
        _request_store[ip] = [
            (ts, count) for ts, count in _request_store[ip]
            if ts > cutoff_time
        ]


def get_request_count(ip: str, window: int) -> int:
    """Get the total number of requests in the time window"""
    clean_old_requests(ip, window)
    return sum(count for _, count in _request_store[ip])


def rate_limit(
    max_requests: int = DEFAULT_RATE_LIMIT,
    window: int = DEFAULT_WINDOW,
    key_func: Callable[[], str] | None = None
):
    """
    Rate limiting decorator for Flask routes
    
    Args:
        max_requests: Maximum number of requests allowed in the time window
        window: Time window in seconds
        key_func: Optional function to generate a custom rate limit key
                 (defaults to IP address)
    
    Usage:
        @app.route('/api/endpoint')
        @rate_limit(max_requests=10, window=60)
        def my_endpoint():
            return {'data': 'value'}
    
    Example with custom key:
        @rate_limit(max_requests=5, window=60, key_func=lambda: request.headers.get('API-Key'))
        def api_endpoint():
            return {'data': 'value'}
    """
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            # Get the rate limit key (IP address or custom key)
            if key_func:
                key = key_func()
            else:
                key = get_client_ip()
            
            # Get current request count
            current_count = get_request_count(key, window)
            
            # Check if limit exceeded
            if current_count >= max_requests:
                log.warning(
                    "rate_limit.exceeded",
                    key=key,
                    count=current_count,
                    limit=max_requests,
                    endpoint=request.endpoint,
                )
                
                return jsonify({
                    'error': 'Rate limit exceeded',
                    'message': f'Too many requests. Limit: {max_requests} per {window} seconds',
                    'retry_after': window,
                }), 429
            
            # Record this request
            current_time = time.time()
            _request_store[key].append((current_time, 1))
            
            # Execute the route handler
            return f(*args, **kwargs)
        
        return wrapped
    return decorator


def rate_limit_by_endpoint(limits: Dict[str, Tuple[int, int]]):
    """
    Apply different rate limits based on endpoint patterns
    
    Args:
        limits: Dictionary mapping endpoint patterns to (max_requests, window) tuples
    
    Usage:
        limits = {
            '/api/v1/telemetry': (50, 60),  # 50 requests per minute
            '/api/v1/sessions': (100, 60),   # 100 requests per minute
        }
        
        @app.before_request
        def apply_rate_limits():
            return rate_limit_by_endpoint(limits)()
    """
    def decorator():
        endpoint = request.endpoint
        if not endpoint:
            return None
        
        # Find matching limit
        for pattern, (max_req, window) in limits.items():
            if pattern in request.path:
                return rate_limit(max_req, window)(lambda: None)()
        
        return None
    
    return decorator


# Preset rate limit decorators for common use cases
def rate_limit_strict(f):
    """Strict rate limit: 10 requests per minute"""
    return rate_limit(max_requests=10, window=60)(f)


def rate_limit_moderate(f):
    """Moderate rate limit: 50 requests per minute"""
    return rate_limit(max_requests=50, window=60)(f)


def rate_limit_relaxed(f):
    """Relaxed rate limit: 100 requests per minute"""
    return rate_limit(max_requests=100, window=60)(f)


def rate_limit_per_hour(max_requests: int = 1000):
    """Rate limit per hour"""
    def decorator(f):
        return rate_limit(max_requests=max_requests, window=3600)(f)
    return decorator
