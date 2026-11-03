import os
import re
import shlex
import threading
import uuid
from multiprocessing import Queue
from typing import List
from .executor import Executor

import enoslib as en

# Strips ANSI escape sequences, carriage returns, and rich/spinner control codes
_ANSI_RE = re.compile(r'\x1b(?:\[[0-9;?]*[ -/]*[@-~]|[@-_])|[\r]')

_SSH_HINT = ("\nHint: if every node failed at the same time, check ~/.ssh/config: with 'ControlMaster auto' and no "
             "'ControlPersist', the ProxyCommand to the gateway (e.g. access.grid5000.fr) is multiplexed through the "
             "first ssh process that opened it, and every tunnel dies when that process exits. Add 'ControlPersist 10m' "
             "(or 'ControlMaster no') for the gateway host.")

def ssh_parameters(machine, extra_vars: dict = {}):
    """How ansible reaches an enoslib Host, as SSHExecutor overrides.

    The variables come from enoslib's own inventory, the one it gives ansible (ansible_host, user, port, key, and the
    gateways as a ProxyCommand in ansible_ssh_common_args), with extra_vars on top as for ansible.

    :return: "local" for a local host, None for a host ansible does not reach with ssh, else a dict of
             hostname, username, port, identityfile and proxycommand
    """
    from enoslib.enos_inventory import EnosInventory
    v = dict(EnosInventory(roles={"all": [machine]}).get_host(machine.alias).get_vars())
    v.update(extra_vars)
    connection = v.get("ansible_connection", "ssh")
    if connection == "local":
        return "local"
    if connection not in ("ssh", "smart", "paramiko"):
        return None
    proxy = None
    args = shlex.split(v.get("ansible_ssh_common_args", "")) + shlex.split(v.get("ansible_ssh_extra_args", ""))
    for i, a in enumerate(args):
        opt = a[2:] if a.startswith("-o") and len(a) > 2 else args[i + 1] if a == "-o" and i + 1 < len(args) else ""
        key, _, value = opt.partition("=")
        if key.lower() == "proxycommand":
            proxy = value
        elif key.lower() == "proxyjump":
            hops = value.split(",")
            proxy = "ssh -W %h:%p " + ("-J " + ",".join(hops[:-1]) + " " if len(hops) > 1 else "") + hops[-1]
    return dict(hostname=v.get("ansible_host", machine.address),
                username=v.get("ansible_user", v.get("ansible_ssh_user", machine.user)),
                port=int(v.get("ansible_port") or 22),
                identityfile=v.get("ansible_ssh_private_key_file"),
                proxycommand=proxy)


# pid files of the commands whose en.run_command has not returned yet. Killers travel through a
# multiprocessing manager queue (pickled), but are used in the process running the exec threads.
_running = set()


class EnoslibKiller:
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


class EnoslibExecutor(Executor):
    """Runs scripts on an enoslib Host with en.run_command (an ansible play per command).

    Ansible returns the output of a command when it ends, so EVENT lines are only seen then. For tests that wait for
    events (waitfor=), give ssh hosts to npf.run(..., enoslib_ssh=True): they then use NPF's SSH executor.
    """
    live_output = False

    def __init__(self, machine, extra_vars: dict = {}):
        super().__init__()
        self.machine = machine
        self.extra_vars = extra_vars
        import npf.globals
        path = npf.globals.get_options().experiment_folder or "results"
        if path[-1] != '/':
            path += '/'
        self.path = path
        # Suppress ansible's rich spinner — it hangs in non-terminal environments (Jupyter)
        en.set_config(ansible_stdout="noop")

    def exec(self, cmd: str, bin_paths: List[str] = [],
             queue: Queue = None, options=None,
             stdin=None, timeout=None, sudo=False,
             testdir=None, event=None, title=None, env={}, virt="", nokill=False
             ) -> [int, str, str, int]:
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

        # As with the other executors, the script is killed at its timeout. Its output (and its EVENTs) only comes
        # back when it ends, so without it a script waiting for an EVENT of a script that never ends would wait forever.
        limit = "timeout -k 5 %d " % int(timeout) if timeout else ""
        cmd = "mkdir -p " + self.path + " && cd " + self.path + " && " + limit + "$S " + virt + " bash -c '" + \
              path_cmd + cmd.replace("'", "'\"'\"'") + "'"
        # Whether sudo is needed depends on the remote user, not on the local one
        if sudo:
            cmd = 'S=; [ "$(id -u)" != 0 ] && command -v sudo >/dev/null 2>&1 && S="sudo -E"; ' + cmd
        else:
            cmd = 'S=; ' + cmd

        pid_file = None
        if queue:
            # Background the command, save its PID so EnoslibKiller can kill it later.
            # If the process dies from a signal (exit > 128), exit 0 so enoslib doesn't
            # log a spurious ERROR for an intentional kill.
            pid_file = f"/tmp/npf-{uuid.uuid4().hex}.pid"
            cmd = (f"{cmd} & _npf_pid=$!; printf '%s' $_npf_pid > {pid_file}; "
                   f"wait $_npf_pid; _rc=$?; [ $_rc -gt 128 ] && [ ! -f {pid_file} ] && exit 0; "
                   f"rm -f {pid_file}; exit $_rc")

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
            queue.put(EnoslibKiller(self.machine, pid_file))

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
        with en.actions(roles=self.machine) as a:
            a.file(path=dest_dir, state="directory", become=sudo)
            a.copy(dest=dest_file, content=content, become=sudo)
        return True
