import sys
import os

# Ensure root workspace directory is in sys.path so modules like app, db can be imported
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from app import app

# Vercel serverless requires the WSGI app exposed at module level
# Both 'app' and 'handler' are supported by Vercel's Python runtime
handler = app
