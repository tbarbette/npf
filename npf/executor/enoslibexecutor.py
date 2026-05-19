import os
import pwd
import re
import threading
import uuid
from multiprocessing import Queue, Event
from typing import List
from .executor import Executor

import enoslib as en

# Strips ANSI escape sequences, carriage returns, and rich/spinner control codes
_ANSI_RE = re.compile(r'\x1b(?:\[[0-9;?]*[ -/]*[@-~]|[@-_])|[\r]')


class EnoslibKiller:
    """Kills a remote process launched via en.run_command."""

    def __init__(self, machine, pid_file):
        self.machine = machine
        self.pid_file = pid_file
        self._pid = None

    def _fetch_pid(self):
        if self._pid is None:
            try:
                r = en.run_command(f"cat {self.pid_file}", roles=self.machine, on_error_continue=True)
                if r and r[0].rc == 0:
                    self._pid = r[0].stdout.strip()
            except Exception:
                pass
        return self._pid

    def _signal_and_kill(self, sigspec):
        pid = self._fetch_pid()
        if pid:
            try:
                # Remove pid_file first: the wrapper uses its absence as proof the kill was intentional
                en.run_command(f"rm -f {self.pid_file}; kill {sigspec} -- -{pid} 2>/dev/null; kill {sigspec} {pid} 2>/dev/null; true",
                               roles=self.machine, on_error_continue=True)
            except Exception:
                pass

    def kill(self):
        self._signal_and_kill("-9")

    def force_kill(self):
        self._signal_and_kill("-15")

    def is_alive(self):
        pid = self._fetch_pid()
        if not pid:
            return False
        try:
            r = en.run_command(f"kill -0 {pid} 2>/dev/null && echo alive || echo dead",
                               roles=self.machine, on_error_continue=True)
            return bool(r) and r[0].stdout.strip() == "alive"
        except Exception:
            return False


class EnoslibExecutor(Executor):
    def __init__(self, machine, extra_vars: dict = {}):
        super().__init__()
        self.machine = machine
        self.extra_vars = extra_vars
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

        env = env.copy()
        env.update(os.environ)
        if bin_paths:
            if not sudo:
                env["PATH"] = ':'.join([cwd + '/' + path if not os.path.abspath(path) else path for path in bin_paths]) + ":" + env["PATH"]
            else:
                cmd = 'export PATH=' + ':'.join([cwd + '/' + path if not os.path.abspath(path) else path for path in bin_paths]) + ":" + '$PATH\n' + cmd

        if options is not None and options.show_cmd:
            print("Executing (PATH+=%s) :\n%s" % (':'.join(bin_paths), cmd.strip()))

        if sudo and pwd.getpwuid(os.getuid()).pw_name != "root":
            cmd = "sudo -E " + virt + "  bash -c '" + cmd.replace("'", "'\"'\"'") + "'"
        else:
            cmd = virt + " bash -c '" + cmd.replace("'", "'\"'\"'") + "'"

        pid_file = None
        if queue:
            # Background the command, save its PID so EnoslibKiller can kill it later.
            # If the process dies from a signal (exit > 128), exit 0 so enoslib doesn't
            # log a spurious ERROR for an intentional kill.
            pid_file = f"/tmp/npf-{uuid.uuid4().hex}.pid"
            cmd = (f"{cmd} & _npf_pid=$!; printf '%s' $_npf_pid > {pid_file}; "
                   f"wait $_npf_pid; _rc=$?; [ $_rc -gt 128 ] && [ ! -f {pid_file} ] && exit 0 || exit $_rc")
        elif timeout:
            # Fallback: no killer available, rely on timeout
            cmd = f"timeout {int(timeout)} {cmd}"

        kwargs = {"extra_vars": self.extra_vars} if self.extra_vars else {}
        result_holder = [None]
        error_holder = [None]

        def _run():
            try:
                result_holder[0] = en.run_command(cmd, roles=self.machine, on_error_continue=True, **kwargs)
            except en.errors.EnosUnreachableHostsError as e:
                error_holder[0] = e

        t = threading.Thread(target=_run, daemon=True)
        t.start()

        if queue and pid_file:
            queue.put(EnoslibKiller(self.machine, pid_file))

        t.join()

        if error_holder[0]:
            e = error_holder[0]
            err = str(e)
            print(f"Host {self.machine.address} is unreachable: {e}")
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
            return -1, "", "", -1

        p = result_holder[0][0]
        stdout_clean = _ANSI_RE.sub('', p.stdout)
        for line in stdout_clean.splitlines():
            self.searchEvent(line, event)
            if options and not options.quiet:
                self._print(title, line.rstrip(), True)

        return p.status, stdout_clean, p.stderr, p.rc

    def writeFile(self, filename, path_to_root, content, sudo=False):
        with en.actions(roles=self.machine) as a:
            a.copy(dest=filename, content=content)
        return True
