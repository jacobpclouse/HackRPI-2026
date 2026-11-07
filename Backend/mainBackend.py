from pathlib import Path

from flask import Flask, send_from_directory


# GLOBAL VAR
HOST_URL = "127.0.0.1"
PORT_NUMBER = 5000

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "Frontend"
ASSETS_DIR = FRONTEND_DIR / "assets"

app = Flask(__name__, static_folder=str(ASSETS_DIR), static_url_path="/assets")


@app.route("/")
def classic_screen():
    return send_from_directory(FRONTEND_DIR, "classic.html")


if __name__ == "__main__":
    app.run(host=HOST_URL, port=PORT_NUMBER)
    # app.run(host="127.0.0.1", port=5000)
