# Let's overengineer git clone

Git and `git clone` are fast, easy-to-use and reliable tools that every developer uses daily. 

Well, you might ask, how can I make it microservice based, unnecessary complex and totally insecure?

Great question! Let's get going. 

## How is it going to work?
We'll use Docker to launch a web service, which will then
launch another container via docker-dind whenever a request comes in to clone the repository into a shared volume. 
We'll then return the repo as a tar file via download in the browser. 

## Part 1: Docker rocker
Docker is a great tool, and it's well known the "c" in Docker stands for cool, so we don't really have another choice.
Let's create a minimal Dockerfile and docker-compose.yaml that uses docker-dind, 
so we can launch another container from our container.

```dockerfile
FROM python:3.12
```

Just 1 line, beautiful. 

```yaml
services:
  web:
    build:
      context: .
    depends_on:
      - docker

  docker:
    image: docker:dind
    privileged: true
```

This launches our minimal Dockerfile as a container named web, and the `docker-dind` image as a container named docker.
Let's launch this and see what happens. Once I run `docker compose up` it produces lots of output, which I didn't read,
but nothing crashes, so I assume everything is fine.

Next we'll try to connect to the docker container from our web container using the docker-py library. To do so we'll
add a `requirements.txt` which contains just that.

```requirements
docker
```

Once again, 1 line, KISSing hard today. 

Let's update our Dockerfile to install the requirements.

```dockerfile
FROM python:3.12
WORKDIR /app
COPY requirements.txt /app
RUN pip install -r requirements.txt
```

You might ask, shouldn't we create a user with the proper permissions to not run as root? 
Nonsense I say! Security is costly and money is tight right now. Also I can never remember if it's `adduser` or 
`useradd` and I'm too lazy to look it up right now.

Moving on, let's create a minimal python script to connect to our docker container. Create a new file `app.py`
with the following content:

```python
import docker
client = docker.DockerClient.from_env()
client.info()
```

And update the `Dockerfile`:

```dockerfile
FROM python:3.12
WORKDIR /app
COPY requirements.txt /app
RUN pip install -r /app/requirements.txt
COPY app.py /app
```

And our `docker-compose.yaml`:

```yaml
services:
  web:
    build:
      context: .
    depends_on:
      - docker
    command: python app.py

  docker:
    image: docker:dind
    privileged: true

```

Let's run `docker compose up --build` again. 

Aaaaaand this time we do get an error :-/

```
web-1  | Traceback (most recent call last):
web-1  |   File "/app/app.py", line 2, in <module>
web-1  |     client = docker.DockerClient.from_env()
web-1  |              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
web-1  |   File "/usr/local/lib/python3.12/site-packages/docker/client.py", line 94, in from_env
web-1  |     return cls(
web-1  |            ^^^^
web-1  |   File "/usr/local/lib/python3.12/site-packages/docker/client.py", line 45, in __init__
web-1  |     self.api = APIClient(*args, **kwargs)
web-1  |                ^^^^^^^^^^^^^^^^^^^^^^^^^^
web-1  |   File "/usr/local/lib/python3.12/site-packages/docker/api/client.py", line 207, in __init__
web-1  |     self._version = self._retrieve_server_version()
web-1  |                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
web-1  |   File "/usr/local/lib/python3.12/site-packages/docker/api/client.py", line 230, in _retrieve_server_version
web-1  |     raise DockerException(
web-1  | docker.errors.DockerException: Error while fetching server API version: ('Connection aborted.', FileNotFoundError(2, 'No such file or directory'))

```

Something about a missing file while creating the docker client. Turns out docker by default tries to connect to the docker daemon via a socket file
that is usually located at `/var/run/docker.sock`. We don't want to connect via socket though, but via network using TCP. 
Let's add an env var to our web container to tell it to connect to our docker container that way.


```yaml
services:
  web:
    build:
      context: .
    depends_on:
      - docker
    command: python app.py
    environment:
      - DOCKER_HOST=tcp://docker:2375

  docker:
    image: docker:dind
    privileged: true
```

Here we tell our web container to contact the docker container at port 2375 for all things docker. 
Let's launch our container and see what happens. 

```bash
web-1  | Traceback (most recent call last):
web-1  |   File "/app/app.py", line 2, in <module>
web-1  |     client = docker.DockerClient.from_env()
web-1  |              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
web-1  |   File "/usr/local/lib/python3.12/site-packages/docker/client.py", line 94, in from_env
web-1  |     return cls(
web-1  |            ^^^^
web-1  |   File "/usr/local/lib/python3.12/site-packages/docker/client.py", line 45, in __init__
web-1  |     self.api = APIClient(*args, **kwargs)
web-1  |                ^^^^^^^^^^^^^^^^^^^^^^^^^^
web-1  |   File "/usr/local/lib/python3.12/site-packages/docker/api/client.py", line 207, in __init__
web-1  |     self._version = self._retrieve_server_version()
web-1  |                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
web-1  |   File "/usr/local/lib/python3.12/site-packages/docker/api/client.py", line 230, in _retrieve_server_version
web-1  |     raise DockerException(
web-1  | docker.errors.DockerException: Error while fetching server API version: HTTPConnectionPool(host='docker', port=2375): Max retries exceeded with url: /version (Caused by NewConnectionError('<urllib3.connection.HTTPConnection object at 0x7785357ea840>: Failed to establish a new connection: [Errno 111] Connection refused'))
```

Fail again, fail differently. The good news is that setting that env var seem to have changed things, the bad news is that 
it still doesn't work. Even worse - we'll have to read some log output to figure things out. As I wrote earlier
we try to connect to port 2375, let's see what our docker container has to say about that:

```bash
[tons of output omitted]
docker-1  | time="2024-05-26T11:26:56.427080454Z" level=info msg="API listen on [::]:2376"
```

Huh, so we try to connect to port 2375 but Docker listens on 2376. Let's change our settings and try again:

```yaml
services:
  web:
    build:
      context: .
    depends_on:
      - docker
    command: python app.py
    environment:
      - DOCKER_HOST=tcp://docker:2376  # changed 2375 to 2376

  docker:
    image: docker:dind
    privileged: true
```

This time we get the same error:

```bash
web-1     | Traceback (most recent call last):
web-1     |   File "/app/app.py", line 2, in <module>
web-1     |     client = docker.DockerClient.from_env()
web-1     |              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
web-1     |   File "/usr/local/lib/python3.12/site-packages/docker/client.py", line 94, in from_env
web-1     |     return cls(
web-1     |            ^^^^
web-1     |   File "/usr/local/lib/python3.12/site-packages/docker/client.py", line 45, in __init__
web-1     |     self.api = APIClient(*args, **kwargs)
web-1     |                ^^^^^^^^^^^^^^^^^^^^^^^^^^
web-1     |   File "/usr/local/lib/python3.12/site-packages/docker/api/client.py", line 207, in __init__
web-1     |     self._version = self._retrieve_server_version()
web-1     |                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
web-1     |   File "/usr/local/lib/python3.12/site-packages/docker/api/client.py", line 230, in _retrieve_server_version
web-1     |     raise DockerException(
web-1     | docker.errors.DockerException: Error while fetching server API version: HTTPConnectionPool(host='docker', port=2375): Max retries exceeded with url: /version (Caused by NewConnectionError('<urllib3.connection.HTTPConnection object at 0x71bfcb29e4e0>: Failed to establish a new connection: [Errno 111] Connection refused'))
web-1 exited with code 1
docker-1  | time="2024-05-26T11:29:13.608513462Z" level=info msg="[graphdriver] using prior storage driver: overlay2"
docker-1  | time="2024-05-26T11:29:13.609697417Z" level=info msg="Loading containers: start."
docker-1  | time="2024-05-26T11:29:14.093074384Z" level=info msg="Default bridge (docker0) is assigned with an IP address 172.17.0.0/16. Daemon option --bip can be used to set a preferred IP address"
docker-1  | time="2024-05-26T11:29:14.152889851Z" level=info msg="Loading containers: done."
docker-1  | time="2024-05-26T11:29:14.163966006Z" level=info msg="Docker daemon" commit=ef1912d containerd-snapshotter=false storage-driver=overlay2 version=26.1.2
docker-1  | time="2024-05-26T11:29:14.164129406Z" level=info msg="Daemon has completed initialization"
docker-1  | time="2024-05-26T11:29:14.206453110Z" level=info msg="API listen on /var/run/docker.sock"
docker-1  | time="2024-05-26T11:29:14.206482325Z" level=info msg="API listen on [::]:2376"

```

It turns out that since our 2 containers launch at the same time, the web container tries to connect to the docker container before
the docker daemon is ready to accept connections.

We could obviously overengineer a solution to try and poll until the server is ready or do some other fancy tricks,
but this "Over engineering git clone" and not "Over engineering git clone and waiting for a service to be ready" so 
we'll just hit em with the ol' reliable `time.sleep`.

Let's add a 3-second wait before the client attempts to connect to the daemon:

```python
import docker
import time

time.sleep(3)
client = docker.DockerClient.from_env()
print(client.info())
```

Alright, third time's a charm:

```bash
web-1     | Traceback (most recent call last):
web-1     |   File "/app/app.py", line 5, in <module>
web-1     |     client = docker.DockerClient.from_env()
web-1     |              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
web-1     |   File "/usr/local/lib/python3.12/site-packages/docker/client.py", line 94, in from_env
web-1     |     return cls(
web-1     |            ^^^^
web-1     |   File "/usr/local/lib/python3.12/site-packages/docker/client.py", line 45, in __init__
web-1     |     self.api = APIClient(*args, **kwargs)
web-1     |                ^^^^^^^^^^^^^^^^^^^^^^^^^^
web-1     |   File "/usr/local/lib/python3.12/site-packages/docker/api/client.py", line 207, in __init__
web-1     |     self._version = self._retrieve_server_version()
web-1     |                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
web-1     |   File "/usr/local/lib/python3.12/site-packages/docker/api/client.py", line 230, in _retrieve_server_version
web-1     |     raise DockerException(
web-1     | docker.errors.DockerException: Error while fetching server API version: 400 Client Error for http://docker:2376/version: Bad Request ("Client sent an HTTP request to an HTTPS server.")
```

... well maybe not. While sleeping did fix the problem that the docker daemon wasn't ready yet a whole different problem
popped up. Docker expects us to connect via HTTPS, while we want to connect via TCP. Stupid security-minded developers.
Here we have 2 options: either configure things properly, mount certs where they belong and use HTTPS like a real
programmer or just tell the Docker daemon to accept connections via TCP. Obviously we'll use the latter.

We'll do so by overriding the entrypoint of the docker container like this:

```yaml
services:
  web:
    build:
      context: .
    depends_on:
      - docker
    command: python app.py
    environment:
      - DOCKER_HOST=tcp://docker:2376

  docker:
    image: docker:dind
    privileged: true
    entrypoint: dockerd --host=tcp://0.0.0.0:2376 --tls=false
```

We basically tell the Docker daemon to listen for connections on all interfaces on port 2376 using TCP and to not
use TLS.

Okay, this time it should work. Let's run `docker comppose up` again.

Ignoring the tons of output that warn us how insecure this approach is and that we potentially expose our machine and
that we should definitely not do this at all, we should see the following:

```text
[insane amount of output skipped]
web-1     | {'ID': '6b5b0018-26a5-4054-8dbd-03b91dde98c1', 'Containers': 0, 'ContainersRunning': 0, [...]}
```

Nice! We finally managed to connect to the remote docker daemon. 

### Part 2: Putting the genie into the flask

Now we'll focus on updating our `app.py` to launch a container that clones the git repo into a volume,
compresses that repo into a tar archive and then have the user download that repo via their browser.
We'll use flask to handle the HTTP server side of things. 

We'll add flask to our requirements.txt, and restart our stack.

```requirements
docker
flask
```

#### Interlude: `docker compose` is watching (for) us
Back in the day when computers were made from wood and powered by steam, we'd usually mount our code into the container 
and then somehow restart the flask process if a file changed. No more! Starting with version 2.22 docker compose 
has built-in capabilities to watch files and restart the affected containers if necessary. 
We'll use this feature from here on to automatically reload our container. 

Here is the updated `docker-compose.yaml`:

```yaml
services:
  web:
    build:
      context: .
    working_dir: /app
    environment:
      - DOCKER_HOST=tcp://docker:2376
    depends_on:
      - docker
    develop:  # new line
      watch:  # new line 
        - action: rebuild  # new line
          path: app.py  # new line

  docker:
    image: docker:dind
    privileged: true
    entrypoint: dockerd --host=tcp://0.0.0.0:2376 --tls=false
```

And from now on we'll use `docker compose up --watch` to have docker compose rebuild and replace the web container whenever
`app.py` gets changed. 

#### Hello World

The last step of our adventure will be to implement the logic behind all this:

* launch a new container
* run git clone for the selected repository
* copy the downloaded repository from the created container into the web container
* tar the repository
* return the tar file in the HTTP response

Let's start by updating our `app.py` to include the basic flask logic

```python
from flask import Flask, send_file

app = Flask(__name__)

@app.route("/")
def hello_world():
    return "Hello world"
```

We'll also need to update our docker-compose.yaml to launch flask and forward the required ports.

```yaml
services:
  web:
    build:
      context: .
    command: flask run
    ports:
      - 5000:5000
    working_dir: /app
    environment:
      - FLASK_RUN_HOST=0.0.0.0
      - DOCKER_HOST=tcp://docker:2376
    depends_on:
      - docker
    develop:
      watch:
        - action: rebuild
          path: app.py

  docker:
    image: docker:dind
    privileged: true
    entrypoint: dockerd --host=tcp://0.0.0.0:2376 --tls=false
```

Note: it might be necessary to restart docker compose once more, so it picks up the updated ports and command settings.

Alright, now we should be able to visit `http://localhost:5000` and be greeted by a classic programming slogan.

So far so good, but it could be a bit more dockier for my taste, so let's launch a container on every request,
which then echoes "Hello world", which will then be returned to our web container, which will then be returned
as part of the HTTP response. 

```python
from flask import Flask, send_file
import docker

app = Flask(__name__)


@app.route("/")
def hello_world():
    client = docker.DockerClient.from_env()
    return client.containers.run("ubuntu", "echo Hello world!")
```

That's better! Now once you reload the page, you'll have to endure some enterprise load times (TM) until you'll be 
served that trusty "Hello world", since first the Ubuntu container needs to be downloaded and launched, but that's
obviously better than not overengineering. 

#### Let's get cloning

Okay, so we have a web container, and we are able to launch Docker containers from that web container. All that is left
is find a way to launch git as a container, and we're good to go. Thankfully the good people of alpine linux have 
provided such container, which we'll use from here on. 

```python
from flask import Flask, send_file
import docker

app = Flask(__name__)

REPO = "https://github.com/pallets/flask.git"


@app.route("/")
def hello_world():
    client = docker.DockerClient.from_env()

    return client.containers.run(
        "alpine/git",
        f"clone {REPO}",
    )
```

Reloading `http://localhost:5000` does ... something. Not that there would be any output to prove it, 
but since that the request takes a moment something must have happened. 

Under the hood, we launched the `alpine/git` container, which then cloned the flask repo, but given the transient
nature of the container, once `git clone` finished the container stopped, and we have no chance of accessing the
downloaded data :-(.

Once again we have 2 possible ways to proceed: somehow wait after git clone, and run `docker cp` to copy all the data
from the container into the web container, or, rather simply download the data onto a volume that is shared between
the containers, so we can access it even after the container shuts down. Since the first one is pretty tricky, and
I'm lazy and this article is quite long already let's go with the second approach. Here is the updated `docker-compose.yaml`

```yaml
services:
  web:
    build:
      context: .
    command: flask run
    ports:
      - 5000:5000
    working_dir: /app
    environment:
      - FLASK_RUN_HOST=0.0.0.0
      - DOCKER_HOST=tcp://docker:2376
    depends_on:
      - docker
    volumes:
      - data:/data
    develop:
      watch:
        - action: rebuild
          path: app.py

  docker:
    image: docker:dind
    privileged: true
    entrypoint: dockerd --host=tcp://0.0.0.0:2376 --tls=false
    volumes:
      - data:/data

volumes:
  data: {}
```

Cool cool cool. We have created a volume named `data`, which is mounted in both the web and docker container, and which
we'll later also mount inside the `alpine/git` container.

Our `app.py` should look like this:

```python
from flask import Flask, send_file
import docker

app = Flask(__name__)

REPO = "https://github.com/pallets/flask.git"


@app.route("/")
def hello_world():
    client = docker.DockerClient.from_env()

    client.containers.run(
        "alpine/git",
        f"clone {REPO} /data",
        remove=True,
        volumes=[
            "/data:/data"
        ]
    )

    return "Cloned successfully"
```

So now we launch the `alpine/git` container with `remove=True` which makes sure that the container is deleted after running
and with the volume setting, so whatever gets cloned while running should be available in our web container afterward.

Let's check it out, open `http://localhost:5000` once more, which should take a moment, and you should see `Cloned successfully`.

Then to see if the data is available run

```bash
$ docker compose run web ls /data
[+] Creating 1/0
 ✔ Container docker-1  Running                                                                                                                                                           0.0s 
CHANGES.rst  CODE_OF_CONDUCT.md  CONTRIBUTING.rst  LICENSE.txt	README.md  docs  examples  pyproject.toml  requirements  requirements-skip  src  tests	tox.ini
```

Well if it isn't the freshly cloned flask repo inside our web container!

Nearly done, now all that is left is to wrap everything into a tar archive and return it in the HTTP response. We'll 
also make sure everything gets downloaded into a separate temporary directory so if 2 users will ever send a request
at the same time, those 2 requests will not overwrite each other. Here's the code


````python
import io
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
````

Here we first create a temporary directory, which will be removed after the request is done,
we clone the repo, and then tar the whole folder into an archive which we then return. Sweet!


# Closing thoughts

I'll leave it as an exercise to the reader to add a form that makes the repo input dynamic. 

The whole code can be found here. Thank you for reading this far, until the next time. 
