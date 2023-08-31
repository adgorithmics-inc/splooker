#!/usr/bin/python3

import json
import argparse
import os
import subprocess
import logging
import socket
import uuid

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

EMPTY_CONFIG = {
    "start_port": 8000,
    "current_port": 8001,
    "max_ports": 10,
    "containers": {}
}


class Settings:
    values = {}

    def get(self, name):
        return self.values[name]

    def set(self, name, value):
        self.values[name] = value


settings = Settings()


def check_server(ip, port):
    try:
        s = socket.create_connection((ip, port), timeout=1)
        s.close()
        return True
    except (ConnectionRefusedError, TimeoutError, socket.timeout):
        return False


def load_json(path):
    with open(path, "r") as f:
        return json.loads(f.read())


def load_configuration():
    config_path = os.path.join(settings.get("base_path"), "splooker.json")
    with open(config_path, "r") as f:
        return json.loads(f.read())


def save_configuration(configuration):
    config_path = os.path.join(settings.get("base_path"), "splooker.json")
    with open(config_path, "w") as f:
        f.write(json.dumps(configuration, indent=2))


def create_nginx_config(name, port):
    with open(os.path.join("/", "etc", "nginx", "sites-enabled", f"{name}.conf"), "w") as f:
        f.write(f"upstream {name} {{ server localhost:{port}; }}")


def run_docker_command(name, port, image, command, docker_args=None):
    if not docker_args:
        docker_args = []

    for index, arg in enumerate(docker_args):
        if "$port" in arg:
            docker_args[index] = arg.replace("$port", str(port))

    uid = str(uuid.uuid4()).split("-")[0]
    name = f"{name}-{uid}"
    command_args = ["docker", "run", *docker_args, "-d", "--name", name, image, *command]
    docker_cmd = subprocess.run(command_args, capture_output=True, text=True)

    if docker_cmd.returncode > 0:
        raise ValueError(docker_cmd.stderr)

    return docker_cmd.stdout.strip()


def ensure_directory_exists(dir_path):
    log.info("Creating directory %s", dir_path)
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)


def validate_nginx():
    if subprocess.run(["nginx", "-t"], capture_output=True).returncode != 0:
        raise SystemError("Unable to verify new nginx configuration.")


def restart_nginx():
    if subprocess.run(["nginx", "-s", "reload"], capture_output=True).returncode != 0:
        raise SystemError("Unable to reload nginx.")


def get_free_port():
    config = load_configuration()
    start_port = config["start_port"]
    max_ports = config["max_ports"]
    max_port = start_port + max_ports
    used_ports = [int(container_info['port']) for container_info in config['containers'].values()]
    next_port = config["current_port"] + 1

    if len(used_ports) >= max_ports:
        raise ValueError("No more ports available. Consider increasing max_ports.")

    while True:

        if next_port > max_port:
            next_port = start_port

        if next_port in used_ports:
            next_port += 1
            continue

        return next_port


def run(name):
    config_path = os.path.join(settings.get("config_path"), f"{name}.json")

    if not os.path.exists(config_path):
        raise ValueError(f"Configuration {config_path} not found")

    configuration = load_json(config_path)

    port = get_free_port()

    # Create nginx configuration.
    create_nginx_config(name=name, port=port)

    # Make sure it's all valid
    validate_nginx()

    # Finally, start the application.
    docker_id = run_docker_command(
        name=name,
        port=port,
        image=configuration["image"],
        command=configuration["command"],
        docker_args=configuration["docker_args"]
    )

    max_retries = settings.get("max_retries")

    for i in range(0, 15):
        log.info("Checking if a server is listening on %s %s/%s", port, i + 1, max_retries)
        if check_server("127.0.0.1", port):
            log.info("Server is listening on %s", port)
            break

    restart_nginx()

    config = load_configuration()

    if old_config := config["containers"].get(name):

        old_id = old_config["id"]
        log.info("Killing old container %s", old_id)

        if subprocess.run(["docker", "rm", "--force", old_id], capture_output=True).returncode != 0:
            log.error("Failed to kill old Docker instance.")

    config["containers"][name] = {
        "id": docker_id,
        "port": port
    }
    config["current_port"] = port

    save_configuration(configuration=config)


def bootstrap():
    ensure_directory_exists(settings.get("base_path"))
    ensure_directory_exists(settings.get("config_path"))

    with open(os.path.join(settings.get("base_path"), "splooker.json"), "w") as f:
        f.write(json.dumps(EMPTY_CONFIG, indent=2))


def main():
    settings.set("base_path", os.path.join("/", "etc", "splooker"))
    settings.set("max_retries", 15)

    parser = argparse.ArgumentParser(description="splooker utility")

    parent_parser = argparse.ArgumentParser(add_help=False)
    parent_parser.add_argument("--config", required=False)

    subparsers = parser.add_subparsers(dest="command", required=True)

    # Setup command
    subparsers.add_parser("setup", parents=[parent_parser])

    # Run command
    run_parser = subparsers.add_parser("run", parents=[parent_parser])
    run_parser.add_argument("--name", required=True, help="Name of the service")

    args = parser.parse_args()

    if args.config:
        settings.set("base_path", args.config)

    settings.set("config_path", os.path.join(settings.get("base_path"), "services"))

    if args.command == "setup":
        bootstrap()
    elif args.command == "run":
        run(name=args.name)
    else:
        log.error("Invalid command %s", args.command)


if __name__ == '__main__':
    main()
