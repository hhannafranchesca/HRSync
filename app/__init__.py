from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
import os
import requests
from dotenv import load_dotenv
load_dotenv()


app = Flask(__name__)

app.config['SECRET_KEY'] = os.getenv("SECRET_KEY")

app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("DATABASE_URL")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['MAIL_DEFAULT_SENDER'] = os.getenv("MAIL_DEFAULT_SENDER")
RESEND_API_KEY = os.getenv("RESEND_API_KEY")

# Flask-Mail configuration
# app.config['MAIL_SERVER'] = os.getenv("MAIL_SERVER", "smtp.gmail.com")
# app.config['MAIL_PORT'] = int(os.getenv("MAIL_PORT", 587))
# app.config['MAIL_USE_TLS'] = os.getenv("MAIL_USE_TLS", "True").lower() in ["true", "1", "yes"]
# app.config['MAIL_USE_SSL'] = os.getenv("MAIL_USE_SSL", "False").lower() in ["true", "1", "yes"]
# app.config['MAIL_USERNAME'] = os.getenv("MAIL_USERNAME")
# app.config['MAIL_PASSWORD'] = os.getenv("MAIL_PASSWORD")
# app.config['MAIL_DEFAULT_SENDER'] = os.getenv("MAIL_DEFAULT_SENDER")


db = SQLAlchemy(app)
# mail = Mail(app) 

bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'

migrate = Migrate(app, db)




@login_manager.user_loader
def load_user(user_id):
    from app.models import Users  # Import Users here to avoid circular import
    return Users.query.get(int(user_id))



# -----------------------------
# Resend Email Integration
# -----------------------------
class Message:
    """Drop-in replacement for Flask-Mail Message."""
    def __init__(self, subject="", recipients=None):
        self.subject = subject
        self.recipients = recipients or []
        self.body = ""

class Mail:
    """Drop-in replacement for Flask-Mail mail object."""
    @staticmethod
    def send(msg):
        if not msg.recipients:
            raise ValueError("No recipients specified")

        url = "https://api.resend.com/emails"
        headers = {
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json"
        }

        data = {
            "from": app.config['MAIL_DEFAULT_SENDER'],
            "to": msg.recipients,  # send all recipients at once
            "subject": msg.subject,
            "html": msg.body.replace("\n", "<br>")
        }

        response = requests.post(url, headers=headers, json=data)
        if response.status_code >= 400:
            print(f"Failed to send email: {response.text}")
        else:
            print(f"Email sent successfully: {response.text}")



# Create a mail object to use like Flask-Mail
mail = Mail()


from app import routes
