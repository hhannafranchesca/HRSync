from dotenv import load_dotenv
import os
from app import app

load_dotenv()



#TO ACTIVATE DEBUGG MODE
if __name__ == "__main__":
    # Get port from environment variable (Railway provides this automatically)
    port = int(os.environ.get("PORT", 5000))
    
    # Run Flask on all interfaces and correct port
    app.run(host="0.0.0.0", port=port, debug=True)