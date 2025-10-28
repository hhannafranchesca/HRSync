from dotenv import load_dotenv
import os

load_dotenv()
from app import app



#TO ACTIVATE DEBUGG MODE
if __name__ == "__main__":
    app.run(debug=True)