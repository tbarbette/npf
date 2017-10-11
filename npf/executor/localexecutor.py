import os
import pwd
import signal
from multiprocessing import Queue, Event
from subprocess import PIPE, Popen, TimeoutExpired
from typing import List

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
        except ProcessLookupError:
            return False
        return True

class LocalExecutor:
    def __init__(self):
        pass

    def exec(self, cmd, terminated_event:Event, bin_paths : List[str]=[], queue: Queue = None, options = None, stdin = None, timeout = None, sudo = False, testdir=None):
        if testdir is not None:
            os.chdir("..")

        cwd = os.getcwd()
        env = os.environ.copy()
        if bin_paths:
            if not sudo:
                env["PATH"] = ':'.join([cwd + '/' + path for path in bin_paths]) + ":" + env["PATH"]
            else:
                cmd = 'export PATH=' + ':'.join([cwd + '/' + path for path in bin_paths]) + ":" + '$PATH\n' + cmd

        if options is not None and options.show_cmd:
            print("Executing (PATH+=%s) :\n%s" % (':'.join(bin_paths), cmd.strip()))

        if sudo and pwd.getpwuid(os.getuid()).pw_name != "root":
            cmd = "sudo -E bash -c '"+ cmd.replace("'", "\\'") + "'";

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
            p.stdin.close()
            p.stderr.close()
            p.stdout.close()
            if testdir is not None:
                os.chdir(testdir)
            return pid, s_output, s_err, 0 if terminated_event.is_set() else p.returncode
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