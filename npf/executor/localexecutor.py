import os
import pwd
import signal
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

    def exec(self, cmd, bin_paths : List[str]=[], queue: Queue = None, options = None, stdin = None, timeout = None, sudo = False, testdir=None, event=None, title=None, env = {}, virt="" ):
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


        p = Popen(cmd,
                  stdin=PIPE, stdout=PIPE, stderr=PIPE,
                  shell=True, preexec_fn=os.setsid,
                  env=env)
        pid = p.pid
        pgpid = os.getpgid(pid)

        killer = LocalKiller(pgpid)
        if queue:
            queue.put(killer)
        try:
            s_output, s_err = [x.decode() for x in
                               p.communicate(input = stdin,  timeout=timeout)]
            self.searchEvent(s_output, event)
            if options and options.show_full:
                for line in s_output.splitlines():
                    self._print(title, line, True)
            p.stdin.close()
            p.stderr.close()
            p.stdout.close()
            if testdir is not None:
                os.chdir(testdir)
            return pid, s_output, s_err, 0 if event and event.is_terminated() else p.returncode
        except TimeoutExpired:
            print("Test expired")
            p.terminate()
            p.kill()
            os.killpg(pgpid, signal.SIGKILL)
            os.killpg(pgpid, signal.SIGTERM)
            s_output, s_err = [x.decode() for x in p.communicate()]
            p.stdin.close()
            p.stderr.close()
            p.stdout.close()
            if testdir is not None:
                os.chdir(testdir)
            return 0, s_output, s_err, p.returncode
        except KeyboardInterrupt:
            os.killpg(pgpid, signal.SIGKILL)
            if testdir is not None:
                os.chdir(testdir)
            return -1, s_output, s_err, p.returncode

    def writeFile(self,filename,path_to_root,content):
        f = open(filename, "w")
        f.write(content)
        f.close()
        return True
