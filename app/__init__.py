from flask import Flask
from config import Config
from flask_httpauth import HTTPBasicAuth
from flask_bootstrap import Bootstrap

import settings

app = Flask(__name__)
app.config.from_object(Config)

bootstrap = Bootstrap(app)

auth = HTTPBasicAuth()

@auth.get_password
def get_pw(username):
    if username in users:
        return users.get(username)
    return None

users = {
    settings.GLOBALUSER: settings.GLOBALPASS
}

from app import routes