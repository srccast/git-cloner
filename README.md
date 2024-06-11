# Things I recently learned about docker-in-docker


## Part 1: The basics

Let's say you have a Docker container and inside that container you want to do Docker stuff, like build images
or launch a docker compose stack, what are your options? 

The easiest way is to volume mount the host's Docker socket into the container like this:

```bash
% docker run -v /run/docker.sock:/run/docker.sock -it docker sh  # run from the host system
```

Now let's launch another container from inside the container:

```bash
/ $ docker run -it ubuntu bash  # run from inside the container
root@ec84497b833b:/# # now this shell runs in a container inside the container
```

Okay, so we have a container running the Docker image, and from inside that container launched another container
running the Ubuntu image. Now let's check what that looks like on the host system.

```bash
% docker ps
CONTAINER ID   IMAGE     COMMAND                  CREATED         STATUS         PORTS           NAMES
ec84497b833b   ubuntu    "bash"                   3 minutes ago   Up 3 minutes                   infallible_leavitt
71c5c74aafe3   docker    "dockerd-entrypoint.…"   6 minutes ago   Up 6 minutes   2375-2376/tcp   interesting_napier
```

Interesting, so even though the container was launched from inside another container, they both exist side-by-side
on the host system. At first, I was surprised by this, but it makes sense as we have mounted the `docker.sock` file
of the host system into the Docker container, which obviously is the interface to the Docker service of the host machine.

So our system currently looks like this:

```text
+---------------------------------------------------+
|                 HOST SYSTEM                       |
|   +-------------------+   +--------------------+  |
|   |                   |   |                    |  |
|   |   CONTAINER A     |   |   CONTAINER B      |  |
|   |   RUNS DOCKER     |   |   RUNS UBUNTU      |  |
|   |                   |   |                    |  |
|   +-------------------+   +--------------------+  |
|                                                   |
+---------------------------------------------------+
```

Okay so what happens if we kill Container A? Will container B shut down as well? Let's see

```bash
% docker ps
CONTAINER ID   IMAGE     COMMAND                  CREATED         STATUS         PORTS           NAMES
ec84497b833b   ubuntu    "bash"                   3 minutes ago   Up 3 minutes                   infallible_leavitt
71c5c74aafe3   docker    "dockerd-entrypoint.…"   6 minutes ago   Up 6 minutes   2375-2376/tcp   interesting_napier

% docker stop 71c5c74aafe3
71c5c74aafe3

% docker ps
CONTAINER ID   IMAGE     COMMAND   CREATED          STATUS          PORTS     NAMES
ec84497b833b   ubuntu    "bash"    3 minutes ago   Up 3 minutes             infallible_leavitt

```

Kind of expected, the Docker container was shut down, but the Ubuntu container is still around, as even though
it was launched from the Docker container it still runs on the host system after all and is not tied to the Docker 
container at all.

Running containers from inside containers this way works well, until you either don't have access to the socket or want
Docker daemons that run entirely separate from the host machine's Docker daemon.

### dind

Dind stands for docker-in-docker, and allows to launch a completely separate Docker daemon inside a container. 
The only drawback is that the dind container has to be launched either 

* as a _privileged_ container, meaning that the container has full access to the host system
* or using a different runtime like [sysbox](https://github.com/nestybox/sysbox), which provides stronger isolation
than the default runtime and allows Docker containers to launch a Docker daemon without full system access

For this article we'll use the former approach, running privileged containers.

Let's run such a container and see what happens:

```bash
% docker network create dind-test
% docker run --rm --network dind-test --privileged --name docker docker:dind dockerd --host tcp://0.0.0.0:2375
time="2024-05-29T12:59:58.949314517Z" level=info msg="Starting up"
time="2024-05-29T12:59:58.950601080Z" level=warning msg="Binding to IP address without --tlsverify is insecure and gives root access on this machine to everyone who has access to your network." host="tcp://0.0.0.0:2375"
time="2024-05-29T12:59:58.950617972Z" level=warning msg="Binding to an IP address, even on localhost, can also give access to scripts run in a browser. Be safe out there!" host="tcp://0.0.0.0:2375"
time="2024-05-29T12:59:58.950631948Z" level=warning msg="[DEPRECATION NOTICE] In future versions this will be a hard failure preventing the daemon from starting! Learn more at: https://docs.docker.com/go/api-security/" host="tcp://0.0.0.0:2375"
[....]
time="2024-05-29T13:00:01.190787714Z" level=warning msg="[DEPRECATION NOTICE]: API is accessible on http://0.0.0.0:2375 without encryption.\n         Access to the remote API is equivalent to root access on the host. Refer\n         to the 'Docker daemon attack surface' section in the documentation for\n         more information: https://docs.docker.com/go/attack-surface/\nIn future versions this will be a hard failure preventing the daemon from starting! Learn more at: https://docs.docker.com/go/api-security/"
time="2024-05-29T13:00:01.190814715Z" level=info msg="Docker daemon" commit=ef1912d containerd-snapshotter=false storage-driver=overlay2 version=26.1.2
time="2024-05-29T13:00:01.191038646Z" level=info msg="Daemon has completed initialization"
time="2024-05-29T13:00:01.234500788Z" level=info msg="API listen on [::]:2375"
```

A couple of things to unpack here, first let's break down the launch command:

* `docker run --rm` We launch the docker container, but remove it after it terminates
* `--network dind-test` We HAVE to create a new network for this, and use it as the [default bridge network doesn't support service discovery through a built-in DNS](https://stackoverflow.com/a/41403239)
* `--privileged` The container receives access to the whole system
* `--name docker` The container will be accessible in the network under the name "docker"
* `docker:dind` We run the official Docker image with the dind tag
* `dockerd --host tcp://0.0.0.0:2375` We launch the Docker daemon listening on all interfaces via TCP

Second, as we can see from the numerous warning messages, this approach is super unsecure as now pretty much anyone
can connect to our new daemon. 

> *If that's so unsecure, why are you doing this?*
> 
> Since the Docket network is not exposed and I wanted to keep things simple I chose the insecure approach.
> If you want to use dind on a production system, you MUST use TLS.

Now let's launch another docker container and the run Ubuntu again.

```bash
% docker run --rm --network dind-test -it docker sh
/ $ docker run ubuntu bash
Unable to find image 'ubuntu:latest' locally
latest: Pulling from library/ubuntu
49b384cc7b4a: Pull complete 
Digest: sha256:3f85b7caad41a95462cf5b787d8a04604c8262cdcdf9a472b8c52ef83375fe15
Status: Downloaded newer image for ubuntu:latest
/ $ 
```

Okay, first we launch the Docker container, again in our `dind-test` network, and then we launch a Ubuntu container 
from inside that container.

> *Wait, why does the image need to pulled again?*
> 
> The host Docker daemon and the newly launched Docker daemon do not share their build and image cache, so the
> image needs to downloaded again.
> 

> *Okay, but how does a container know which Docker daemon to connect to?*
> 
> Check [this great stackoverflow answer](https://stackoverflow.com/a/73573049) for a detailed answer.
> tldr: 
>
> * if the DOCKER_HOST env var exists, use whatever is specified there 
> * use unix:///run/docker.sock if it exists
> * use tcp://docker:2375 if no TLS configuration exists
> * use tcp://docker:2376 if a TLS configuration exists

Let's see what at this looks like from our host system:

```bash
% docker ps 
CONTAINER ID   IMAGE         COMMAND                  CREATED          STATUS          PORTS           NAMES
6b5bedaedfeb   docker        "dockerd-entrypoint.…"   2 minutes ago    Up 2 minutes    2375-2376/tcp   elastic_bouman
0abe319c4796   docker:dind   "dockerd-entrypoint.…"   10 minutes ago   Up 10 minutes   2375-2376/tcp   docker
```

Interesting, the Ubuntu container doesn't show up at all. Let's launch another container Docker container to check
the running docker containers on the `docker:dind` container:

```bash
% docker run --network dind-test -it docker sh
/ $ docker ps
CONTAINER ID   IMAGE     COMMAND   CREATED              STATUS              PORTS     NAMES
9f4013ccfe75   ubuntu    "bash"    About a minute ago   Up About a minute             laughing_zhukovsky
```

Just as expected, the Ubuntu container runs entirely separate from the host Docker daemon inside a new Docker daemon
on the `docker:dind` container. Let's visualise this:

```text
+-------------------------------------------------------------------------+
|                       HOST SYSTEM                                       |
| +---------------------+          +------------------------------------+ |
| |   CONTAINER A       |          |   CONTAINER B                      | |
| |   RUNS DOCKER       |          |   RUNS DOCKER:DIND                 | |
| |                     |          |                                    | |
| |                   COMMUNICATES WITH        +------------------+     | |
| |                   --+----------+>          | CONTAINER C      |     | |
| |                     |          |           | RUNS UBUNTU      |     | |
| |                   LAUNCHES     |           |                  |     | |
| |                   --+----------+-----------+------>           |     | |
| |                     |          |           |                  |     | |
| |                     |          |           +------------------+     | |
| +---------------------+          +------------------------------------+ |
+-------------------------------------------------------------------------+
```

So here Container A tells Container B (the `docker:dind` container) to launch a Ubuntu container, which runs
(isolated from the host's Docker daemon) in the daemon launched by the `docker:dind` container.

### Volumes

Something that was odd to me was how volumes are handled, but see for yourself:

```bash
# assuming the docker:dind container still runs
% docker run --network dind-test -it docker sh
/ $ docker run -it -v /tmp:/tmp ubuntu bash
root@e76cea8eead4:/# echo "Hello from Ubuntu" > /tmp/greeting
root@e76cea8eead4:/# 
exit
/ $ ls /tmp/
/ $ 
```

Huh, weird. So we launched another Ubuntu container, but this time we mounted `/tmp` into the container, we then 
created a file in `/tmp` but the file doesn't show up in the launching container. Where is it?

Since the launching container only forwards the command to the actual `docker:dind` container, the volume is shared
between the `docker:dind` container and the Ubuntu container, as we can see here

```bash
% docker exec -it docker sh
/ $ ls /tmp/
greeting
/ $ cat /tmp/greeting 
Hello from Ubuntu
```

That also means that if we want to share a volume between the launching container and the Ubuntu container, we first
have to share a volume between the launching container and the `docker:dind` container, and then when launching the 
Ubuntu container, share volume mount that folder again on the Ubuntu container. 

I was confused about that at first, so I decided to build a small application that uses all those concept together.
Which brings us to part 2:

# Part 2: let's overengineer git clone

We'll build a small Flask service, which will launch a git container whenever a request comes in 
to clone a repository into a shared volume. We'll afterward return the repo as a tar file via download to the user. 

## Let's get coding

From here on we'll use docker compose, since it makes orchestration easier and helps with the small things, like
creating a new network and handle volumes.

Let's create a minimal script which connects to the Docker container and prints some information:

```python
import docker
import time
time.sleep(20)  # give the docker:dind container time to launch

client = docker.DockerClient.from_env()
print(client.info())
```

Then the Dockerfile:

```dockerfile
FROM python:3.12
RUN pip install docker
WORKDIR /app
COPY app.py /app/app.py
```

And our docker-compose.yaml

```yaml
services:
  web:
    build:
      context: .
    depends_on:
      - docker
    command: python /app/app.py
    environment:
      DOCKER_HOST: tcp://docker:2375

  docker:
    image: docker:dind
    privileged: true
    entrypoint: dockerd --host tcp://0.0.0.0:2375

```

This launches our minimal Dockerfile as a container named web, and the `docker:dind` image as a container named docker.

Now let's run this and see what happens when we run `docker compose up`

```text
[output skipped]
web-1     | {'ID': '6b5b0018-26a5-4054-8dbd-03b91dde98c1', 'Containers': 0, 'ContainersRunning': 0, [...]}
```

Nice! We managed to connect to the remote docker daemon. 

### Putting the genie into the flask

Let's implement that previously mentioned Flask service.

First our updated `Dockerfile`, which now installs flask.

```Docker
FROM python:3.12
RUN pip install docker flask
WORKDIR /app
COPY app.py /app/app.py
```
And the new `app.py` to include the basic flask logic

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
    depends_on:
      - docker
    command: flask run
    environment:
      FLASK_RUN_HOST: 0.0.0.0
      DOCKER_HOST: tcp://docker:2375
    ports:
      - 5000:5000

  docker:
    image: docker:dind
    privileged: true
    entrypoint: dockerd --host tcp://0.0.0.0:2375
```

Alright, now we should be able to visit `http://localhost:5000` and be greeted by "Hello world".

So far so good, let's launch a container on every request,
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

Now if we send another request, it'll take longer than before, but after some time we'll see "Hello world!" again.
Like said earlier, the extra time comes from downloading and launching the Ubuntu container. 

### Let's get cloning

Okay, so we have a web container, and we are able to launch Docker containers from that web container. All that is left
is find a way to launch git as a container, and we're good to go. Thankfully the good people of alpine linux have 
provided such container, which we'll use. 

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

Reloading `http://localhost:5000` does ... something. Under the hood, we launched the `alpine/git` container, 
which then cloned the flask repo, but given the transient
nature of the container, once `git clone` finished the container stopped, and we have no chance of accessing the
downloaded data.

Let's add volumes to access the cloned repo.

```yaml
services:
  web:
    build:
      context: .
    depends_on:
      - docker
    command: flask run
    environment:
      FLASK_RUN_HOST: 0.0.0.0
      DOCKER_HOST: tcp://docker:2375
    ports:
      - 5000:5000
    volumes:
      - data:/data

  docker:
    image: docker:dind
    privileged: true
    entrypoint: dockerd --host tcp://0.0.0.0:2375
    volumes:
      - data:/data

volumes:
  data: {}

```

We now have a volume named `data`, which is mounted in both the web and docker container, and which
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
        f"clone {REPO}",
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

Great, it's the cloned repo on the data volume inside the web container.

Nearly done, now all that is left is to wrap everything into a tar archive and return it in the HTTP response. We'll 
also make sure everything gets downloaded into a separate temporary directory so if 2 users will ever send a request
at the same time, those 2 requests will not overwrite each other. Here's the code


```python
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

    with TemporaryDirectory(dir="/data", delete=False) as temp_dir:
        client.containers.run(
            "alpine/git",
            f"clone {REPO} /data",
            volumes=[
                f"{temp_dir}:/data"
            ]
        )

        out_f = io.BytesIO()
        with tarfile.open(fileobj=out_f, mode='w') as f:
            f.add(temp_dir, recursive=True)

        out_f.seek(0)
        return send_file(path_or_file=out_f, mimetype="application/x-tar")
```

Here we first create a temporary directory, which will be removed after the request is done,
we clone the repo, and then tar the whole folder into an archive which we then return. Sweet!


## Closing thoughts

I hope this article helped people that want to use dind but didn't know how to start properly. If you have
any thoughts, comments or spot any errors please contact me at fabian.lange@srccast.de. Thanks for reading, 
until the next time. 

## Further reading

* https://hub.docker.com/_/docker
* https://jpetazzo.github.io/2015/09/03/do-not-use-docker-in-docker-for-ci/
