import io
import logging
import tarfile
from tempfile import TemporaryDirectory

from flask import Flask, send_file
import docker

app = Flask(__name__)

REPO = "https://github.com/pallets/flask.git"


@app.route("/")
def hello_world():
    client = docker.DockerClient.from_env()

    with TemporaryDirectory(dir="/data") as temp_dir:
        client.containers.run(
            "alpine/git",
            f"clone {REPO} {temp_dir}",
            remove=True,
            volumes=[
                "/data:/data"
            ]
        )

        out_f = io.BytesIO()
        with tarfile.open(fileobj=out_f, mode='w') as f:
            f.add(temp_dir, recursive=True)

        out_f.seek(0)
        return send_file(path_or_file=out_f, mimetype="application/x-tar")
