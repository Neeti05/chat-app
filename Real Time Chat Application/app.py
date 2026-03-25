from flask import Flask, render_template, request
from flask_socketio import SocketIO

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app)

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('message')
def handle_message(msg):
    data = {
        "msg": msg,
        "id": request.sid
    }
    socketio.send(data, broadcast=True)

if __name__ == '__main__':
    socketio.run(app, debug=True)