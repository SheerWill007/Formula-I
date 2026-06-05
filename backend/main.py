import sys
import os

# Add src directory to Python path so we can import backend module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from backend import create_app
from backend.config import settings

# Create app instance for gunicorn and direct execution
app = create_app()

if __name__ == "__main__":
    # Get port from environment variable (Render sets PORT), default to 8000 for local development
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=settings.debug)
