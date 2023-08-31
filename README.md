# Splooker

0 downtime Docker deployments on a single instance.

## Pre-requisites

* Docker
* Nginx

## Commands

- `splooker setup` sets up the Splooker environment
- `splooker run --name=myname` runs deployment called `myname`.

## Setting up Splooker

After running `splooker setup` you can place service files in `/etc/splooker/services`.

Then to start your service, run `splooker run --name=api`, 
assuming you placed a service file in `/etc/splooker/services/api.json`.

Automatically Splooker will create an upstream for nginx with the name of your service,
in the above example it would create an upstream called `api`

```text
upstream api { 
    server localhost:8005; 
}
```

The port will be automatically determined, based on what ports are available. 
Splooker will automatically check and reload your nginx configuration.

The first time you run splooker, there is no upstream, you will have to manually
update your existing nginx configuration, then point it to the new upstream.


The default splooker configuration looks like this and is available in `/etc/splooker/splooker.json`.

```json
{
    "start_port": 8000,
    "current_port": 8000,
    "max_ports": 10,
    "containers": {}
}
```

## Example Service File

```json
{
  "image": "your-docker-image",
  "command": [
    "uwsgi",
    "--socket",
    "0.0.0.0:8000",
    "--protocol=http",
    "-w",
    "genie.wsgi:application",
    "--enable-threads"
  ],
  "docker_args": [
    "-p",
    "$port:8000",
    "/opt/my-app"
  ]
}
```