from flask import Flask, render_template, request
from flask_httpauth import HTTPBasicAuth

from bokeh.client import pull_session
from bokeh.embed import server_session

app = Flask(__name__)
auth = HTTPBasicAuth()

users = {
    "ths": "success"
}

@auth.get_password
def get_pw(username):
    if username in users:
        return users.get(username)
    return None

@app.route('/')
def index():
    session = pull_session(url="http://127.0.0.1:5006/myapp")
    # session.document.roots[0].children[1].title.text = "Special Sliders For A Specific User!"
    script = server_session(None, session.id, url='http://127.0.0.1:5006/myapp')
    return render_template("index.html", script=script, template="Flask")

if __name__ == '__main__':
    app.run(port=5000, debug=True)