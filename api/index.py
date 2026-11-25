import sys
import os
import json

# Ensure root workspace directory is in sys.path so modules like app, db can be imported
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from app import app as flask_app

def handler(environ, start_response):
    # Debug hook: if requesting /debug-env or if query string has debug=1
    if environ.get('PATH_INFO') in ('/debug-env', '/api/debug-env') or 'debug=1' in environ.get('QUERY_STRING', ''):
        clean_env = {
            k: str(v) for k, v in environ.items() 
            if not any(secret in k.lower() for secret in ['key', 'secret', 'token', 'pass'])
        }
        body = json.dumps(clean_env, indent=2).encode('utf-8')
        start_response('200 OK', [
            ('Content-Type', 'application/json'),
            ('Content-Length', str(len(body)))
        ])
        return [body]

    # If Vercel set PATH_INFO to /api/index or /api, restore original path if available
    # Vercel passes original requested path in HTTP headers
    raw_path = (
        environ.get('HTTP_X_FORWARDED_URI') or 
        environ.get('HTTP_X_MATCHED_PATH') or 
        environ.get('HTTP_X_NOW_ROUTE_MATCHES') or
        ''
    )
    if (environ.get('PATH_INFO') in ('/api/index', '/api', '/api/index.py') or not environ.get('PATH_INFO')) and raw_path:
        environ['PATH_INFO'] = raw_path

    return flask_app(environ, start_response)

# Vercel looks for 'app' or 'handler'
app = handler
