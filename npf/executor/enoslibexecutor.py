import os
import re
import shlex
import subprocess
import threading
import uuid
from multiprocessing import Queue
from typing import List
from .localexecutor import LocalExecutor, LocalKiller

import enoslib as en
from enoslib.utils import generate_ssh_option_gateway

# Strips ANSI escape sequences, carriage returns, and rich/spinner control codes
_ANSI_RE = re.compile(r'\x1b(?:\[[0-9;?]*[ -/]*[@-~]|[@-_])|[\r]')

# $0=npf $1=pid file $2=script $3=sudo wanted $4=virt prefix $5=working directory.
# As for the docker executor, job control gives the script its own process group (pgid == pid in the pid file) so
# the killer reaches its children. stdin comes from /dev/null as ssh -tt gives the wrapper a terminal.
_WRAPPER = r'''set -m
exec 3>&2 2>/dev/null
mkdir -p "$5" && cd "$5" || exit 1
if [ "$3" = 1 ] && [ "$(id -u)" != 0 ] && command -v sudo >/dev/null 2>&1; then S="sudo -E"; else S=; fi
$S $4 bash -c "$2" </dev/null 2>&3 &
p=$!
echo $p > "$1"
wait $p
r=$?
rm -f "$1"
exit $r'''

_SSH_HINT = ("\nHint: if every node failed at the same time, check ~/.ssh/config: with 'ControlMaster auto' and no "
             "'ControlPersist', the ProxyCommand to the gateway (e.g. access.grid5000.fr) is multiplexed through the "
             "first ssh process that opened it, and every tunnel dies when that process exits. Add 'ControlPersist 10m' "
             "(or 'ControlMaster no') for the gateway host.")


class EnoslibKiller:
    """Kills a script started by EnoslibExecutor over ssh: killing the local ssh client alone would leave it running."""

    def __init__(self, executor, pid_file, local_killer):
        self.executor = executor
        self.pid_file = pid_file
        self.local_killer = local_killer

    def _signal(self, sig):
        # The script may have printed (and triggered the kill) before the wrapper wrote the pid file, and a signal
        # sent while the script forks may miss it (seen on macOS), hence the wait and the retries
        f = self.pid_file
        self.executor.run_raw(f'i=0; while [ ! -s {f} ] && [ $i -lt 20 ]; do sleep 0.1; i=$((i+1)); done; '
                              f'p=$(cat {f} 2>/dev/null); [ -n "$p" ] && for i in 1 2 3 4 5; do '
                              f'kill -{sig} -$p 2>/dev/null; kill -{sig} $p 2>/dev/null; sleep 0.1; '
                              f'kill -0 -$p 2>/dev/null || kill -0 $p 2>/dev/null || break; done; true')

    def kill(self):
        if self.is_alive():
            self._signal("KILL")

    def force_kill(self):
        if self.is_alive():
            self._signal("TERM")
            try:
                self.local_killer.force_kill()
            except (ProcessLookupError, PermissionError):
                pass

    def is_alive(self):
        # The ssh client returns when the remote script does, no need to ask the node
        return self.local_killer.is_alive()


# Serializes the opening of shared ssh connections, so two executors for the same host do not open two masters
_master_lock = threading.Lock()

# pid files of the commands whose en.run_command has not returned yet. Killers travel through a
# multiprocessing manager queue (pickled), but are used in the process running the exec threads.
_running = set()


class EnoslibAnsibleKiller:
    """Kills a remote process launched via en.run_command.

    Every remote call is a full ansible play (seconds through a gateway), so the killer checks
    locally whether the en.run_command of the script returned, and never contacts the node for a
    script that already finished.
    """

    def __init__(self, machine, pid_file):
        self.machine = machine
        self.pid_file = pid_file
        self._pid = None

    def _signal_and_kill(self, sigspec):
        if not self.is_alive():
            return
        # Remove pid_file first: the wrapper uses its absence as proof the kill was intentional.
        # The pid is echoed back so a second signal can be sent once the file is gone.
        read_pid = self._pid if self._pid else f"$(cat {self.pid_file} 2>/dev/null)"
        try:
            r = en.run_command(f"_p={read_pid}; rm -f {self.pid_file}; [ -n \"$_p\" ] && "
                               f"{{ kill {sigspec} -- -$_p 2>/dev/null; kill {sigspec} $_p 2>/dev/null; echo $_p; }}; true",
                               roles=self.machine, on_error_continue=True)
            if r and "stdout" in r[0].payload and r[0].stdout.strip():
                self._pid = r[0].stdout.strip()
        except Exception:
            pass

    def kill(self):
        self._signal_and_kill("-9")

    def force_kill(self):
        self._signal_and_kill("-15")

    def is_alive(self):
        return self.pid_file in _running


class EnoslibExecutor(LocalExecutor):
    """Runs scripts on an enoslib Host.

    Hosts reached with ssh (ansible's default) are driven with the ssh client directly, with the connection parameters
    enoslib gives ansible, and LocalHost-like ones locally: output is streamed as it comes (so EVENT/waitfor work)
    and a command costs an ssh session instead of a whole ansible play. Other ansible connection types go through
    en.run_command, which only returns the output once the script ends.
    """

    def __init__(self, machine, extra_vars: dict = {}):
        super().__init__()
        self.machine = machine
        self.extra_vars = extra_vars
        import npf.globals
        path = npf.globals.get_options().experiment_folder or "results"
        if path[-1] != '/':
            path += '/'
        self.path = path
        # Host variables as ansible sees them: extra_vars win over the host's extra
        self.vars = {**machine.extra, **extra_vars}
        connection = self.vars.get("ansible_connection", "ssh")
        self.connection = "ssh" if connection in ("ssh", "smart") else connection
        # Suppress ansible's rich spinner — it hangs in non-terminal environments (Jupyter)
        en.set_config(ansible_stdout="noop")

    def _ssh_args(self) -> List[str]:
        """The host's own ssh arguments, as ansible would get them."""
        v = self.vars
        common = v.get("ansible_ssh_common_args")
        if common is None:
            # What enoslib passes to ansible (see enoslib.enos_inventory)
            common = "-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
            if v.get("forward_agent"):
                common += " -o ForwardAgent=yes"
            user = self.machine.user
            common += " " + generate_ssh_option_gateway([
                (v.get("gateway"), v.get("gateway_user", user), v.get("gateway_port")),
                (v.get("internal_gateway"), v.get("internal_gateway_user", user), v.get("internal_gateway_port"))])
        return shlex.split(common) + shlex.split(v.get("ansible_ssh_extra_args", ""))

    def ssh_command(self, tty=False, master=False) -> List[str]:
        """The ssh command line reaching the host, built like the one ansible would use."""
        v = self.vars
        # ssh keeps the first value given for an option: the host's own arguments come before NPF's defaults.
        # Scripts and kills go through a shared master connection (see _ensure_master), so they do not pay a
        # handshake through the gateways, but never become the master themselves.
        cmd = ["ssh"] + self._ssh_args() + [
            "-o", "BatchMode=yes", "-o", "LogLevel=ERROR", "-o", "ConnectTimeout=30", "-o", "ServerAliveInterval=15",
            "-o", "ControlPersist=10m", "-o", "ControlPath=/tmp/npf-cm-%C", "-e", "none"]
        cmd += ["-M", "-N", "-f"] if master else ["-o", "ControlMaster=no"]
        if tty:
            # A terminal keeps the output of the remote programs line-buffered, as ansible's -tt did
            cmd.append("-tt")
        user = v.get("ansible_user", v.get("ansible_ssh_user", self.machine.user))
        port = v.get("ansible_port", self.machine.port)
        keyfile = v.get("ansible_ssh_private_key_file", self.machine.keyfile)
        if user:
            cmd += ["-l", str(user)]
        if port:
            cmd += ["-p", str(port)]
        if keyfile:
            cmd += ["-i", str(keyfile)]
        return cmd + ["--", str(v.get("ansible_host", self.machine.address))]

    def _ensure_master(self):
        """Opens the shared connection to the host if it is not up, in its own session.

        If the ssh of a script became the master, the ProxyCommand it started would stay in the process group of
        that script for the life of the master: the killer would wait for it, and kill it with the script."""
        if self.connection != "ssh" or any("ControlMaster" in a or "ControlPath" in a for a in self._ssh_args()):
            return
        with _master_lock:
            check = self.ssh_command()
            if subprocess.run(check[:-2] + ["-O", "check"] + check[-2:], stdin=subprocess.DEVNULL,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
                return
            # With -f, ssh returns once the master is up in the background (it keeps stderr, so no pipe here)
            try:
                ret = subprocess.run(self.ssh_command(master=True), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL, start_new_session=True, timeout=60).returncode
            except subprocess.TimeoutExpired:
                ret = 124
            if ret != 0:
                print(f"WARNING: could not open a shared ssh connection to {self.machine.address}, every command "
                      f"will open its own")

    def _command(self, argv, tty=False) -> List[str]:
        """Command line running argv on the host."""
        if self.connection == "local":
            return argv
        self._ensure_master()
        return self.ssh_command(tty) + [" ".join(shlex.quote(a) for a in argv)]

    def run_raw(self, cmd, timeout=30, input=None):
        """Runs a small shell command on the host (kills, file writes). Returns (returncode, stdout)."""
        try:
            r = subprocess.run(self._command(["sh", "-c", cmd]), capture_output=True, text=True, input=input,
                               timeout=timeout)
        except subprocess.TimeoutExpired:
            return 124, ""
        return r.returncode, r.stdout

    def exec(self, cmd: str, bin_paths: List[str] = [],
             queue: Queue = None, options=None,
             stdin=None, timeout=None, sudo=False,
             testdir=None, event=None, title=None, env={}, virt="", nokill=False
             ) -> [int, str, str, int]:
        if self.connection not in ("ssh", "local"):
            return self._exec_ansible(cmd, bin_paths, queue, options, timeout, sudo, testdir, event, title, env, virt)

        if testdir:
            cmd = "mkdir -p " + testdir + " && cd " + testdir + ";\n" + cmd
        if not title:
            title = self.machine.address

        # Only NPF's own variables: the local os.environ (PATH, HOME, tokens...) must not leak to the remote node
        script = self.get_env_str(env.copy(), options) + cmd
        path_list = [p if os.path.isabs(p) else os.path.join(self.path, p) for p in (bin_paths or [])]
        if path_list:
            script = 'export PATH="%s:$PATH"\n' % (':'.join(path_list)) + script

        if options is not None and options.show_cmd:
            print("Executing on %s (PATH+=%s) :\n%s" % (self.machine.address, ':'.join(path_list), cmd.strip()))

        pid_file = f"/tmp/npf-{uuid.uuid4().hex}.pid"
        argv = self._command(["sh", "-c", _WRAPPER, "npf", pid_file, script, "1" if sudo else "0", virt, self.path],
                             tty=True)
        pid, out, err, ret = self._run(" ".join(shlex.quote(a) for a in argv), dict(os.environ), queue, options,
                                       timeout, event, title,
                                       make_killer=lambda pgpid: EnoslibKiller(self, pid_file, LocalKiller(pgpid)))
        # With -tt, the script's stdout and stderr both come in `out`, `err` only has ssh's own messages
        if self.connection == "ssh" and ret == 255 and err.strip():
            print(f"Could not run the script on {self.machine.address}: {err.strip()}" + _SSH_HINT)
        return pid, _ANSI_RE.sub('', out), err, ret

    def _exec_ansible(self, cmd, bin_paths, queue, options, timeout, sudo, testdir, event, title, env, virt):
        if testdir:
            cmd = "mkdir -p " + testdir + " && cd " + testdir + ";\n" + cmd

        if not title:
            title = self.machine.address

        # Only NPF's own variables: the local os.environ (PATH, HOME, tokens...) must not leak to the remote node
        env = env.copy()
        env_str = self.get_env_str(env, options)
        cmd = env_str + cmd

        if bin_paths is None:
            bin_paths = []
        path_list = [p if os.path.isabs(p) else os.path.join(self.path, p) for p in bin_paths]

        if path_list:
            path_cmd = 'export PATH="%s:$PATH"\n' % (':'.join(path_list))
        else:
            path_cmd = ''

        if options is not None and options.show_cmd:
            print("Executing (PATH+=%s) :\n%s" % (':'.join(path_list), cmd.strip()))

        if sudo:
            cmd = "sudo -E " + virt + "  bash -c '" + path_cmd + cmd.replace("'", "'\"'\"'") + "'"
        else:
            cmd = virt + " bash -c '" + path_cmd + cmd.replace("'", "'\"'\"'") + "'"

        cmd = "mkdir -p " + self.path + " && cd " + self.path + " && " + cmd

        pid_file = None
        if queue:
            # Background the command, save its PID so EnoslibAnsibleKiller can kill it later.
            # If the process dies from a signal (exit > 128), exit 0 so enoslib doesn't
            # log a spurious ERROR for an intentional kill.
            pid_file = f"/tmp/npf-{uuid.uuid4().hex}.pid"
            cmd = (f"{cmd} & _npf_pid=$!; printf '%s' $_npf_pid > {pid_file}; "
                   f"wait $_npf_pid; _rc=$?; [ $_rc -gt 128 ] && [ ! -f {pid_file} ] && exit 0; "
                   f"rm -f {pid_file}; exit $_rc")
        elif timeout:
            # Fallback: no killer available, rely on timeout
            cmd = f"timeout {int(timeout)} {cmd}"

        kwargs = {"extra_vars": self.extra_vars} if self.extra_vars else {}
        result_holder = [None]
        error_holder = [None]
        if pid_file:
            _running.add(pid_file)

        def _run():
            try:
                result_holder[0] = en.run_command(cmd, roles=self.machine, on_error_continue=True, **kwargs)
            except en.errors.EnosUnreachableHostsError as e:
                error_holder[0] = e
            finally:
                _running.discard(pid_file)

        t = threading.Thread(target=_run, daemon=True)
        t.start()

        if queue and pid_file:
            queue.put(EnoslibAnsibleKiller(self.machine, pid_file))

        t.join()

        if error_holder[0]:
            return self._unreachable("UNREACHABLE", str(error_holder[0]))

        p = result_holder[0][0]
        # With on_error_continue, an unreachable host is returned as a result without stdout/rc
        if p.status == "UNREACHABLE" or "stdout" not in p.payload:
            return self._unreachable(p.status, str(p.payload.get("msg", p.payload)))
        stdout_clean = _ANSI_RE.sub('', p.stdout)
        for line in stdout_clean.splitlines():
            self.searchEvent(line, event)
            if options and not options.quiet:
                self._print(title, line.rstrip(), True)

        return p.status, stdout_clean, p.stderr, p.rc

    def _unreachable(self, status, err):
        """Report a connection failure as a failed script (rc 255, like ssh) instead of crashing the whole test."""
        print(f"Host {self.machine.address} is unreachable: {err}")
        if "Could not resolve hostname" in err and "grid5000" in err:
            print(
                "\nHint: Grid5000 hostnames are only reachable from inside G5K. "
                "If connecting from outside, add a ProxyCommand to ~/.ssh/config:\n\n"
                "    Host *.grid5000.fr\n"
                "        User <your-g5k-login>\n"
                "        ProxyCommand ssh <your-g5k-login>@access.grid5000.fr -W %h:%p\n"
                "        ForwardAgent no\n\n"
                "See: https://www.grid5000.fr/w/Getting_Started"
                "#Recommended_configuration_of_the_SSH_client"
            )
        elif "Shared connection" in err or "closed" in err or "banner exchange" in err or err.endswith("via ssh: "):
            print(_SSH_HINT)
        return status, "", err, 255

    def writeFile(self, filename, path_to_root, content, sudo=False):
        import npf.globals
        dest_dir = os.path.join(npf.globals.experiment_path(), path_to_root)
        dest_file = os.path.join(dest_dir, filename)
        print("Sending %s to %s" % (dest_file, self.machine.address))
        if self.connection in ("ssh", "local"):
            s = 'S=; [ "$(id -u)" != 0 ] && S=sudo; ' if sudo else 'S=; '
            ret, _ = self.run_raw(f"{s}$S mkdir -p {shlex.quote(dest_dir)} && $S tee {shlex.quote(dest_file)} >/dev/null",
                                  input=content)
            return ret == 0
        with en.actions(roles=self.machine) as a:
            a.file(path=dest_dir, state="directory", become=sudo)
            a.copy(dest=dest_file, content=content, become=sudo)
        return True
