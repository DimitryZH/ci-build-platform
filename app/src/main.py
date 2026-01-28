from flask import Flask
app = Flask(__name__)

@app.route("/")
def hello():
    return "CI Build Platform on GCP — Docker Image Built Successfully!"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
