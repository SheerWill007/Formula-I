import sys
import os

# Add src directory to Python path so we can import backend module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from backend import create_app

if __name__ == "__main__":
    from backend.config import settings
    app = create_app()
    app.run(host="0.0.0.0", port=8000, debug=settings.debug)
