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
    def __init__(self, machine):
        super().__init__()
        self.machine = machine
        #en.set_config(ansible_stdout="noop")
        #p = en.run_command("echo 'test'", roles=machine)
        #print(p)

    def exec(self, cmd : str, bin_paths : List[str]=[],
             queue: Queue = None, options = None,
             stdin = None, timeout = None, sudo = False,
             testdir = None, event = None, title = None, env = {}, virt = "" ,
        ) -> [int, str, str, int]:
        """Runs a command in local

        Args:
            cmd (_type_): The command to run
            bin_paths (List[str], optional): Paths to binaries, to be added to $PATH. Defaults to [].
            queue (Queue, optional): Killing queue, to add this script to the list of script to be killed when the test is finished. Defaults to None.
            options (_type_, optional): Global options. Defaults to None.
            stdin (_type_, optional): stdin to echo to the script. Defaults to None.
            timeout (_type_, optional): Timeout after which the execution is cancelled. Defaults to None.
            sudo (bool, optional): If su priviledge should be gain. Defaults to False.
            testdir (_type_, optional): Path in which to execute tests. Defaults to None.
            event (_type_, optional): Event queue. Defaults to None.
            title (_type_, optional): Title for the script. Defaults to None.
            env (dict, optional): Env array. Defaults to {}.
            virt (str, optional): Virtualisation decorator (eg namespaces). Defaults to "".

        Returns:
            [int, str, str, int]: pid, stdout, stderr, return code
        """
        if testdir:
            cmd = "mkdir -p " + testdir + " && cd " + testdir + ";\n" + cmd;

        if not title:
            title = self.machine.address
        
        print(cmd)

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
            cmd = "sudo -E " + virt + "  bash -c '"+ cmd.replace("'", "'\"'\"'") + "'";
        else:
            cmd = virt + " bash -c '"+ cmd.replace("'", "'\"'\"'") + "'";

        try:
            p = en.run_command(cmd, roles=self.machine)
        except en.errors.EnosFailedHostsError as e:
            print("Error while running command!")
            print(e)
            return -1,"","",-1

        p = p[0]
        for line in p.stdout.splitlines():

            #line = line.decode()
            self.searchEvent(line, event)
            if options and not options.quiet:
                self._print(title, line.rstrip(), True)

        return p.status, p.stdout, p.stderr, p.rc

    def writeFile(self,filename,path_to_root,content,sudo=False):
        with en.actions(roles=self.machine) as a:
            a.copy(dest=filename, content=content)

        return True
