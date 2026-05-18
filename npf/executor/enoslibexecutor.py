import os
import pwd
import signal
import select
from multiprocessing import Queue, Event
from subprocess import PIPE, Popen, TimeoutExpired
from typing import List
from .executor import Executor
from pathlib import Path

import enoslib as en



class EnoslibExecutor(Executor):
    def __init__(self, machine, extra_vars: dict = {}):
        super().__init__()
        self.machine = machine
        self.extra_vars = extra_vars

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
            cmd = virt + " bash -c '"+ cmd.replace("'", "'\"'\"'") + "'";

#        if queue:
#            killer = EnoslibKiller(pgpid)
#            queue.put(killer)

        try:
            p = en.run_command(cmd, roles=self.machine, extra_vars=self.extra_vars)
        except (en.errors.EnosUnreachableHostsError, en.errors.EnosFailedHostsError) as e:
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

        p = p[0]
        for line in p.stdout.splitlines():
            self.searchEvent(line, event)
            if options and not options.quiet:
                self._print(title, line.rstrip(), True)

        return p.status, p.stdout, p.stderr, p.rc

    def writeFile(self, filename, path_to_root, content, sudo=False):
        with en.actions(roles=self.machine) as a:
            a.copy(dest=filename, content=content)
        return True
