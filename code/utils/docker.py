import docker
import subprocess
import time

def ensure_docker_running(max_retries=3, retry_interval=5):
    for attempt in range(max_retries):
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                text=True,
                check=True
            )
            print("Docker service is running")
            return True
        except subprocess.CalledProcessError as e:
            print(f"Docker service is not running (attempt {attempt + 1}/{max_retries}): {e.stderr}")
            if attempt < max_retries - 1:
                print(f"Retrying after {retry_interval} seconds...")
                time.sleep(retry_interval)
        except FileNotFoundError:
            print("Docker CLI not installed, please install Docker Desktop")
            raise Exception("Docker CLI is unavailable")
    raise Exception("Docker service is unavailable, please check Docker Desktop or CLI configuration")

def start_neo4j_container():
    client = docker.from_env()
    container_name = "neo4j-db"
    try:
        container = client.containers.get(container_name)
        if container.status != "running":
            container.start()
            print("Neo4j container started")
        else:
            print("Neo4j container is already running")
    except docker.errors.NotFound:
        client.containers.run(
            image="neo4j:latest",
            name=container_name,
            ports={"7474/tcp": 7474, "7687/tcp": 7687},
            environment=[
                "NEO4J_AUTH=neo4j/password",
                "NEO4JLABS_PLUGINS=[\"apoc\"]",  # APOC plugin installed
                "NEO4J_dbms_security_procedures_unrestricted=apoc.*"  # allows APOC process
            ],
            detach=True
        )
        print("Neo4j container created and started with APOC")
        time.sleep(15)  
    except docker.errors.APIError as e:
        print(f"Docker API error: {str(e)}")
        raise
    return client
