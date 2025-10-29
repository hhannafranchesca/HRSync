from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from flask_mail import Mail
import os

app = Flask(__name__)

app.config['SECRET_KEY'] = os.getenv("SECRET_KEY")

app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("DATABASE_URL").strip()
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# Flask-Mail configuration
app.config['MAIL_SERVER'] = os.getenv("MAIL_SERVER", "smtp.gmail.com")
app.config['MAIL_PORT'] = int(os.getenv("MAIL_PORT", 587))
app.config['MAIL_USE_TLS'] = os.getenv("MAIL_USE_TLS", "True").lower() in ["true", "1", "yes"]
app.config['MAIL_USE_SSL'] = os.getenv("MAIL_USE_SSL", "False").lower() in ["true", "1", "yes"]
app.config['MAIL_USERNAME'] = os.getenv("MAIL_USERNAME")
app.config['MAIL_PASSWORD'] = os.getenv("MAIL_PASSWORD")
app.config['MAIL_DEFAULT_SENDER'] = os.getenv("MAIL_DEFAULT_SENDER")


db = SQLAlchemy(app)
mail = Mail(app) 

bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'




migrate = Migrate(app, db)




# DEBUGGING ROUTES (EMERGENCY)
# @app.before_request
# def list_routes():
#     for rule in app.url_map.iter_rules():
#         print(f"Route: {rule} | Methods: {list(rule.methods)}")





from app import routes

@login_manager.user_loader
def load_user(user_id):
    from app.models import Users  # Import Users here to avoid circular import
    return Users.query.get(int(user_id))