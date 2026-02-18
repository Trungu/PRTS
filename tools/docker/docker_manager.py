# docker_manager.py
import subprocess
import os
import uuid

# ---------------------------------------------------------------------------
# Persistent workspace path
# ---------------------------------------------------------------------------
# Calculated relative to this file so the path is correct regardless of the
# working directory the bot process was launched from.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_WORKSPACE_HOST_DIR = os.path.abspath(
    os.path.join(_THIS_DIR, "..", "..", "sandbox_workspace")
)


class DockerManager:
    def __init__(self):
        self.container_name = "ai_sandbox_env"
        self.image = "ai_sandbox_image"
        self.work_dir = "/workspace"
        # Host-side source for the /workspace bind mount.
        # Created automatically on first run if it does not exist.
        self.workspace_host_dir = _WORKSPACE_HOST_DIR
        os.makedirs(self.workspace_host_dir, exist_ok=True)

    def start_container(self):
        """Ensures the sandbox container is running with high security."""
        print(f"[DOCKER] Checking for container '{self.container_name}'...")
        
        # Check if running
        check_cmd = ["docker", "ps", "-q", "-f", f"name={self.container_name}"]
        is_running = subprocess.run(check_cmd, capture_output=True, text=True).stdout.strip()

        if is_running:
            print("[DOCKER] Container is already running.")
            self._ensure_help_file()
            return

        # Check if exists but stopped
        check_stopped = ["docker", "ps", "-aq", "-f", f"name={self.container_name}"]
        is_stopped = subprocess.run(check_stopped, capture_output=True, text=True).stdout.strip()

        if is_stopped:
            print("[DOCKER] Container exists but stopped. Removing...")
            subprocess.run(["docker", "rm", "-f", self.container_name])

        # Start new container
        run_cmd = [
            "docker", "run", "-d", "-t",
            "--name", self.container_name,
            "--runtime=runsc",
            "--network", "none",
            "--memory", "1024m",
            # Disable swap entirely — equals memory cap to prevent limit bypass via swap.
            "--memory-swap", "1024m",
            "--cpus", "2",
            "--cap-drop=ALL",
            "--read-only",
            # Prevent any process inside the container from gaining new privileges
            # (e.g. via setuid binaries).  Critical for a public-facing sandbox.
            "--security-opt", "no-new-privileges:true",

            # Allow writing to /tmp (ephemeral — cleared on container restart).
            "--tmpfs", "/tmp",

            # Persistent workspace — bind-mount the host directory so files
            # survive container restarts and image rebuilds.
            "-v", f"{self.workspace_host_dir}:{self.work_dir}",

            self.image, "bash"
        ]
        
        print(f"[DOCKER CMD] {' '.join(run_cmd)}")
        result = subprocess.run(run_cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print(f"[DOCKER] Sandbox started successfully.")
            self._ensure_help_file()
        else:
            print(f"[DOCKER ERROR] Failed to start: {result.stderr}")

    def _ensure_help_file(self):
        """Copy help.txt to workspace if it's not already there."""
        check = subprocess.run(
            ["docker", "exec", self.container_name, "test", "-f", "/workspace/help.txt"],
            capture_output=True
        )
        if check.returncode != 0:
            subprocess.run(
                ["docker", "exec", self.container_name, "cp", "/home/sandboxuser/help.txt", "/workspace/help.txt"],
                capture_output=True
            )
            print("[DOCKER] help.txt copied to workspace.")

    def execute_command(self, command: str) -> str:
        """Runs a shell command inside the container."""
        print(f"[DOCKER EXEC] Input: {command}")
        
        full_cmd = [
            "docker", "exec",
            # Always run as the non-root sandbox user regardless of image defaults.
            "--user", "sandboxuser",
            # Ensure the working directory is the writable workspace.
            "--workdir", self.work_dir,
            self.container_name,
            "/bin/sh", "-c", command,
        ]
        
        try:
            result = subprocess.run(full_cmd, capture_output=True, text=True, timeout=60)
            output = result.stdout
            if result.stderr:
                output += f"\nSTDERR: {result.stderr}"
            
            if len(output) > 1800:
                output = output[:1800] + "\n...[Output Truncated]"
                
            print(f"[DOCKER EXEC] Output Length: {len(output)}")
            return output if output.strip() else "[Command finished with no output]"
            
        except subprocess.TimeoutExpired:
            return "Error: Command timed out (60s limit). This might mean something went wrong, or that you are using too much compute power."
        except Exception as e:
            return f"Error executing command: {e}"

    def copy_to_container(self, file_bytes: bytes, container_path: str) -> bool:
        """Copies raw bytes into the container at the given path using docker exec + tee."""
        print(f"[DOCKER COPY] Writing {len(file_bytes)} bytes to {container_path}")

        try:
            cmd = [
                "docker", "exec", "-i",
                self.container_name,
                "tee", container_path
            ]
            result = subprocess.run(
                cmd,
                input=file_bytes,
                capture_output=True,
                timeout=60
            )
            if result.returncode == 0:
                print(f"[DOCKER COPY] Successfully wrote to {container_path}")
                return True
            else:
                print(f"[DOCKER COPY ERROR] {result.stderr.decode()}")
                return False
        except subprocess.TimeoutExpired:
            print("[DOCKER COPY ERROR] Timed out writing file to container. This might mean something went wrong, or that you are using too much compute power.")
            return False
        except Exception as e:
            print(f"[DOCKER COPY ERROR] {e}")
            return False

    def get_file_path(self, container_path: str):
        """
        Checks file size first (Limit 8MB), then streams content via cat.
        Replaces 'docker cp' to support tmpfs/memory mounts.
        """
        MAX_BYTES = 7.9 * 1024 * 1024 
        
        print(f"[DOCKER FILE] checking size of {container_path}")

        # 1. Check file size
        size_cmd = ["docker", "exec", self.container_name, "stat", "-c", "%s", container_path]
        size_check = subprocess.run(size_cmd, capture_output=True, text=True)

        if size_check.returncode != 0:
            print(f"[DOCKER FILE] Error: File not found or unreadable.")
            return None

        try:
            file_size = int(size_check.stdout.strip())
        except ValueError:
            return None

        if file_size > MAX_BYTES:
            print(f"[DOCKER FILE] Denied: File is {file_size/1024/1024:.2f}MB (Limit: 8MB)")
            return "TOO_LARGE" 

        # 2. EXTRACT CONTENT via 'cat'
        # 'docker cp' fails on tmpfs. We stream stdout to a local file instead.
        filename = os.path.basename(container_path)
        local_path = f"./temp_{uuid.uuid4()}_{filename}"
        
        print(f"[DOCKER FILE] Streaming {container_path} -> {local_path}")
        
        cat_cmd = ["docker", "exec", self.container_name, "cat", container_path]
        
        try:
            with open(local_path, "wb") as f:
                # Pipe stdout directly to the file, stderr to a pipe to check for errors
                result = subprocess.run(cat_cmd, stdout=f, stderr=subprocess.PIPE)
                
            if result.returncode == 0:
                return local_path
            else:
                err_msg = result.stderr.decode()
                print(f"[DOCKER FILE] Read failed: {err_msg}")
                if os.path.exists(local_path): os.remove(local_path)
                return None
        except Exception as e:
            print(f"[DOCKER FILE] Exception during stream: {e}")
            return None