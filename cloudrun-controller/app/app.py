from flask import Flask, request, jsonify
import subprocess
import os

app = Flask(__name__)

GITHUB_TOKEN = os.environ.get("GITHUB_CONTROLLER_TOKEN")

@app.route("/run", methods=["POST"])
def run():
    token = request.headers.get("X-Controller-Token")
    if token != GITHUB_TOKEN:
        return jsonify({"error": "unauthorized"}), 401

    try:
        tf_dir = "/workspace/terraform"
        subprocess.check_call(["terraform", "init"], cwd=tf_dir)
        subprocess.check_call(["terraform", "apply", "-auto-approve"], cwd=tf_dir)
        return jsonify({"status": "runner provisioning started"}), 200

    except subprocess.CalledProcessError as e:
        return jsonify({"error": "terraform failed", "details": str(e)}), 500

@app.route("/", methods=["GET"])
def health():
    return "Runner Controller is alive", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
