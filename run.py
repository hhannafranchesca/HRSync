import os
from app import app

# Get port from environment variable (Railway provides this automatically)
port = int(os.environ.get("PORT", 5000))

if __name__ == "__main__":
    # Disable debug for Railway production
    app.run(host="0.0.0.0", port=port)
