import os
import pwd
import signal
import select
from multiprocessing import Queue, Event
from subprocess import PIPE, Popen, TimeoutExpired
from typing import List
from .executor import Executor
class LocalKiller:
    def __init__(self, pgpid):
        self.pgpid = pgpid

    def kill(self):
        os.killpg(self.pgpid, signal.SIGKILL)

    def force_kill(self):
        os.killpg(self.pgpid, signal.SIGTERM)

    def is_alive(self):
        try:
            os.killpg(self.pgpid, 0)
        except PermissionError:
            return True
        except ProcessLookupError:
            return False
        return True

class LocalExecutor(Executor):
    def __init__(self):
        super().__init__()

    def exec(self, cmd : str, bin_paths : List[str]=[],
             queue: Queue = None, options = None,
             stdin = None, timeout = None, sudo = False,
             testdir=None, event=None, title=None, env = {}, virt="" ) -> [int, str, str, int]:
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
        if testdir is not None:
            os.chdir("..")
        if not title:
            title = "local"
        cwd = os.getcwd()
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

        outputs = ['', '']

        p = Popen(cmd,
                  stdin=PIPE, stdout=PIPE, stderr=PIPE,
                  shell=True, preexec_fn=os.setsid,
                  env=env)

        select_set = select.poll()
        select_set.register(p.stdout,select.POLLIN)
        select_set.register(p.stderr,select.POLLIN)
        os.set_blocking(p.stdout.fileno(), False)
        os.set_blocking(p.stderr.fileno(), False)
        pid = p.pid
        pgpid = os.getpgid(pid)
        flushing = False

        step = 0.2
        killer = LocalKiller(pgpid)
        if queue:
            queue.put(killer)
        try:
            while True:
                select_set.poll(step * 1000)
                for ichannel, channel in enumerate([p.stdout,p.stderr]):
                    for line in channel.readlines():
                        line = line.decode()
                        outputs[ichannel] += line
                        self.searchEvent(line, event)
                        if options and not options.quiet:
                            self._print(title, line.rstrip(), True)

                #When the program is closed, do one last turn
                if p.poll() is not None or (event and event.is_terminated()):
                    if flushing:
                        break
                    else:
                        flushing = True


                if timeout is not None:
                    timeout -= step
                    if timeout < 0:
                        raise TimeoutExpired(cmd, timeout)

            p.stdin.close()
            p.stderr.close()
            p.stdout.close()
            if testdir is not None:
                os.chdir(testdir)
            return pid, outputs[0], outputs[1], 0 if event and event.is_terminated() else p.returncode
        except TimeoutExpired:
            print("Test expired")
            p.terminate()
            p.kill()
            os.killpg(pgpid, signal.SIGKILL)
            os.killpg(pgpid, signal.SIGTERM)
            p.stdin.close()
            p.stderr.close()
            p.stdout.close()
            if testdir is not None:
                os.chdir(testdir)
            return 0, outputs[0], outputs[1], p.returncode
        except KeyboardInterrupt:
            os.killpg(pgpid, signal.SIGKILL)
            if testdir is not None:
                os.chdir(testdir)
            return -1, outputs[0], outputs[1], p.returncode

    def writeFile(self,filename,path_to_root,content,sudo=False):
        f = open(filename, "w")
        f.write(content)
        f.close()
        return True
