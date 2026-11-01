import atexit
import os
import shlex
import shutil
import subprocess
import tempfile
import time
import urllib.parse
import uuid
from multiprocessing import Queue
from typing import List

from .localexecutor import LocalExecutor

# $0=npf $1=pid file $2=script $3=sudo wanted $4=virt prefix $5=working directory.
# Job control gives the script its own process group (pgid == pid in the pid file) so the killer reaches its
# children. sudo is only used when not root and available.
_WRAPPER = r'''set -m
exec 3>&2 2>/dev/null
mkdir -p "$5" && cd "$5" || exit 1
if [ "$3" = 1 ] && [ "$(id -u)" != 0 ] && command -v sudo >/dev/null 2>&1; then S="sudo -E"; else S=; fi
$S $4 bash -c "$2" 2>&3 &
p=$!
echo $p > "$1"
wait $p'''

_IGNORED = ['.git', '.vimhistory']


class SSHDockerSocket:
    """One ssh connection per remote docker host, forwarding its docker socket to a private local unix socket.

    `docker -H ssh://host` opens a new ssh connection (through the jump hosts of your ssh config, with a handshake each
    time) for every single docker command, and a sweep runs hundreds of them. With this, they all share one connection.
    The remote socket is $NPF_DOCKER_SOCK or /var/run/docker.sock (the user needs access to it, as for docker)."""
    _tunnels = {}

    def __init__(self, host, wait=60):
        self.pid = os.getpid()
        self.dir = tempfile.mkdtemp(prefix="npf-dk-", dir="/tmp")
        self.sock = os.path.join(self.dir, "docker.sock")
        self.proc = subprocess.Popen(self.command(host, self.sock), stdin=subprocess.DEVNULL,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        atexit.register(self.close)
        end = time.time() + wait
        while not os.path.exists(self.sock):
            if self.proc.poll() is not None or time.time() > end:
                err = self.proc.stderr.read() if self.proc.poll() is not None else "timeout"
                self.close()
                raise RuntimeError(err.strip() or "ssh exited")
            time.sleep(0.1)

    @staticmethod
    def command(host, local_sock, remote_sock=None):
        u = urllib.parse.urlsplit(host)
        target = (u.username + "@" if u.username else "") + (u.hostname or "")
        cmd = ["ssh", "-N", "-x", "-o", "BatchMode=yes", "-o", "ExitOnForwardFailure=yes", "-o", "LogLevel=ERROR",
               "-o", "ConnectTimeout=30", "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=4",
               "-L", "%s:%s" % (local_sock, remote_sock or os.environ.get("NPF_DOCKER_SOCK", "/var/run/docker.sock"))]
        if u.port:
            cmd += ["-p", str(u.port)]
        return cmd + ["--", target]

    def close(self):
        if os.getpid() != self.pid:
            return
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        shutil.rmtree(self.dir, ignore_errors=True)

    @classmethod
    def endpoint(cls, host):
        """The docker -H value to use for `host`: the forwarded socket, or host itself if ssh forwarding fails."""
        if host not in cls._tunnels:
            try:
                cls._tunnels[host] = cls(host)
            except (RuntimeError, OSError) as e:
                print("WARNING: could not forward the docker socket of %s (%s), using docker's own ssh transport "
                      "(slower: one ssh connection per command)." % (host, e))
                cls._tunnels[host] = None
        t = cls._tunnels[host]
        return "unix://" + t.sock if t else host


class DockerKiller:
    """Kills a script started with `docker exec`. Killing the docker client alone would leave the script running in the container."""

    def __init__(self, executor, pid_file, local_killer):
        self.executor = executor
        self.pid_file = pid_file
        self.local_killer = local_killer

    def _signal(self, sig):
        script = (f'p=$(cat {self.pid_file} 2>/dev/null); '
                  f'[ -n "$p" ] && {{ kill -{sig} -$p 2>/dev/null; kill -{sig} $p 2>/dev/null; }}; '
                  f'{"rm -f " + self.pid_file if sig == "KILL" else "true"}')
        self.executor.run_raw(script)

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
        ret, _ = self.executor.run_raw(f'p=$(cat {self.pid_file} 2>/dev/null); [ -n "$p" ] && kill -0 $p 2>/dev/null')
        return ret == 0


class DockerExecutor(LocalExecutor):
    """Runs scripts inside an already running container with `docker exec`.

    Two modes, as for SSH nodes:
     - shared (path is None): the experiment folder is bind-mounted in the container at the same absolute path (eg
       `-v $PWD:$PWD`). Files written on the host are seen directly.
     - not shared (path is set): the container has its own copy of the experiment folder at `path`. Files and
       software are copied in with tar, like the SFTP transfer of the SSH executor. This is what GNS3 Docker nodes need.

    `host` is a docker daemon address (eg ssh://user@gns3-server) when the container runs on another machine.
    Needs bash in the container.
    """

    def __init__(self, container, host=None, path=None):
        super().__init__()
        self.container = container
        self.addr = container
        self.host = host
        self.path = path

    @property
    def shared(self):
        return self.path is None

    def _docker(self, *args):
        daemon = []
        if self.host:
            daemon = ["-H", SSHDockerSocket.endpoint(self.host) if self.host.startswith("ssh://") else self.host]
        return ["docker"] + daemon + list(args)

    def _workdir(self):
        """Where the scripts run in the container: the folder in which NPF currently is, translated to the container."""
        if self.shared:
            return os.getcwd()
        import npf.globals
        rel = os.path.relpath(os.getcwd(), os.path.abspath(npf.globals.experiment_path()))
        return os.path.normpath(os.path.join(self.path, rel))

    def exec(self, cmd: str, bin_paths: List[str] = [],
             queue: Queue = None, options=None,
             stdin=None, timeout=None, sudo=False,
             testdir=None, event=None, title=None, env={}, virt="", nokill=False
             ) -> [int, str, str, int]:
        if not title:
            title = self.container

        # Only NPF's variables are exported: the host environment (PATH, HOME...) is meaningless in the container
        script = self.get_env_str(dict(env), options) + cmd
        if bin_paths:
            script = 'export PATH=' + ':'.join(
                p if os.path.isabs(p) else os.path.join(os.path.dirname(self._workdir()), p) for p in bin_paths) + ':$PATH\n' + script

        if options is not None and options.show_cmd:
            print("Executing in %s (PATH+=%s) :\n%s" % (self.container, ':'.join(bin_paths), script.strip()))

        pid_file = f"/tmp/npf-{uuid.uuid4().hex}.pid"
        full = shlex.join(self._docker("exec", "-i", self.container,
                                       "bash", "-c", _WRAPPER, "npf", pid_file, script, "1" if sudo else "0", virt,
                                       self._workdir()))

        return self._run(cmd=full, env=dict(os.environ), queue=queue, options=options, timeout=timeout,
                         event=event, title=title,
                         make_killer=lambda pgpid: DockerKiller(self, pid_file, self._make_killer(pgpid)))

    def run_raw(self, cmd, timeout=30, input=None):
        """Runs a small shell command in the container (node discovery, kills, file transfers). Returns (returncode, stdout)."""
        try:
            r = subprocess.run(self._docker("exec", "-i", self.container, "sh", "-c", cmd),
                               capture_output=True, text=input is None or isinstance(input, str),
                               input=input, timeout=timeout)
        except subprocess.TimeoutExpired:
            return 124, ""
        return r.returncode, r.stdout

    def inspect_ips(self):
        r = subprocess.run(self._docker("inspect", "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}",
                                        self.container), capture_output=True, text=True)
        return r.stdout.split()

    def writeFile(self, filename, path_to_root, content, sudo=False):
        if self.shared:
            return super().writeFile(filename, path_to_root, content, sudo)
        # Like the SSH executor, keep a local copy too
        super().writeFile(filename, path_to_root, content)
        dest_dir = os.path.normpath(os.path.join(self.path, path_to_root))
        ret, _ = self.run_raw("%smkdir -p %s && cat > %s" % ("sudo " if sudo else "", shlex.quote(dest_dir),
                              shlex.quote(os.path.join(dest_dir, filename))), input=content)
        return ret == 0

    def sendFolder(self, path, local=None):
        """Copies a file or folder (relative to `local`, defaults to the current directory) to self.path/path.
        Returns (bytes sent, bytes already up to date), the latter is always 0 as everything is sent."""
        if self.shared:
            return 0, 0
        src_root = local if local else os.getcwd()
        if not os.path.exists(os.path.join(src_root, path)):
            raise FileNotFoundError("Cannot send %s: not found in %s" % (path, src_root))
        dest_root = os.path.normpath(os.path.join(self.path, os.path.dirname(path)))
        tar = subprocess.run(["tar", "-C", src_root, "-cf", "-"] + ["--exclude=" + i for i in _IGNORED] + [path],
                             capture_output=True)
        if tar.returncode != 0:
            raise Exception("tar failed for %s: %s" % (path, tar.stderr.decode(errors="replace")))
        ret, _ = self.run_raw("mkdir -p %s && tar -C %s -xf -" % (shlex.quote(dest_root), shlex.quote(dest_root)),
                              input=tar.stdout, timeout=600)
        if ret != 0:
            raise Exception("Could not send %s to container %s" % (path, self.container))
        return len(tar.stdout), 0

    def deleteFolder(self, path):
        if self.shared:
            return
        target = os.path.normpath(os.path.join(self.path, path))
        if not target.startswith(self.path.rstrip("/") + "/"):
            raise Exception("Refusing to delete %s outside of %s" % (target, self.path))
        self.run_raw("rm -rf %s" % shlex.quote(target))
