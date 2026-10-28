import shlex
import subprocess
import uuid
from multiprocessing import Queue
from typing import List

from .localexecutor import LocalExecutor

# $0=npf $1=pid file $2=script $3=sudo wanted $4=virt prefix.
# Job control gives the script its own process group (pgid == pid in the pid file) so the killer reaches its
# children. sudo is only used when not root and available.
_WRAPPER = r'''set -m
exec 3>&2 2>/dev/null
if [ "$3" = 1 ] && [ "$(id -u)" != 0 ] && command -v sudo >/dev/null 2>&1; then S="sudo -E"; else S=; fi
$S $4 bash -c "$2" 2>&3 &
p=$!
echo $p > "$1"
wait $p'''


def docker_bin():
    return "docker"


class DockerKiller:
    """Kills a script started with `docker exec`. Killing the docker client alone would leave the script running in the container."""

    def __init__(self, container, pid_file, local_pgpid, local_killer):
        self.container = container
        self.pid_file = pid_file
        self.local_pgpid = local_pgpid
        self.local_killer = local_killer

    def _signal(self, sig):
        script = (f'p=$(cat {self.pid_file} 2>/dev/null); '
                  f'[ -n "$p" ] && {{ kill -{sig} -$p 2>/dev/null; kill -{sig} $p 2>/dev/null; }}; '
                  f'{"rm -f " + self.pid_file if sig == "KILL" else "true"}')
        subprocess.run([docker_bin(), "exec", self.container, "sh", "-c", script],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def kill(self):
        self._signal("KILL")
        try:
            self.local_killer.kill()
        except (ProcessLookupError, PermissionError):
            pass

    def force_kill(self):
        self._signal("TERM")
        try:
            self.local_killer.force_kill()
        except (ProcessLookupError, PermissionError):
            pass

    def is_alive(self):
        r = subprocess.run([docker_bin(), "exec", self.container, "sh", "-c",
                            f'p=$(cat {self.pid_file} 2>/dev/null); [ -n "$p" ] && kill -0 $p 2>/dev/null'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return r.returncode == 0


class DockerExecutor(LocalExecutor):
    """Runs scripts inside an already running container with `docker exec`.

    The experiment folder must be bind-mounted in the container at the same absolute path (eg
    `-v $PWD:$PWD`), as with an NFS-shared SSH node. Files are therefore written on the host side and the
    scripts are started from the same working directory inside the container. Needs bash in the container.
    """

    def __init__(self, container):
        super().__init__()
        self.container = container
        self.addr = container

    def exec(self, cmd: str, bin_paths: List[str] = [],
             queue: Queue = None, options=None,
             stdin=None, timeout=None, sudo=False,
             testdir=None, event=None, title=None, env={}, virt="", nokill=False
             ) -> [int, str, str, int]:
        import os
        if not title:
            title = self.container

        # Only NPF's variables are exported: the host environment (PATH, HOME...) is meaningless in the container
        script = self.get_env_str(dict(env), options) + cmd
        if bin_paths:
            script = 'export PATH=' + ':'.join(
                p if os.path.isabs(p) else os.path.join(os.path.dirname(os.getcwd()), p) for p in bin_paths) + ':$PATH\n' + script

        if options is not None and options.show_cmd:
            print("Executing in %s (PATH+=%s) :\n%s" % (self.container, ':'.join(bin_paths), script.strip()))

        pid_file = f"/tmp/npf-{uuid.uuid4().hex}.pid"
        full = shlex.join([docker_bin(), "exec", "-i", "-w", os.getcwd(), self.container,
                           "bash", "-c", _WRAPPER, "npf", pid_file, script, "1" if sudo else "0", virt])

        return self._run(cmd=full, env=dict(os.environ), queue=queue, options=options, timeout=timeout,
                         event=event, title=title,
                         make_killer=lambda pgpid: DockerKiller(self.container, pid_file, pgpid, self._make_killer(pgpid)))

    def run_raw(self, cmd, timeout=30):
        """Runs a small shell command in the container for node discovery. Returns (returncode, stdout)."""
        r = subprocess.run([docker_bin(), "exec", self.container, "sh", "-c", cmd],
                           capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout

    def inspect_ips(self):
        r = subprocess.run([docker_bin(), "inspect", "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}",
                            self.container], capture_output=True, text=True)
        return r.stdout.split()
