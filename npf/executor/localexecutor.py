import os
import pty
import pwd
import termios
import signal
import select
from multiprocessing import Queue, Event
from subprocess import PIPE, Popen, TimeoutExpired
from typing import List
from .executor import Executor
import npf.globals
from pathlib import Path
import time

class LocalKiller:
    def __init__(self, pgpid):
        self.pgpid = pgpid

    def kill(self):
        os.killpg(self.pgpid, signal.SIGKILL)
        # A shell forking when the signal arrives can miss it and go on with the next command (seen on macOS)
        for _ in range(50):
            time.sleep(0.01)
            if not self.is_alive():
                return
            try:
                os.killpg(self.pgpid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                return

    def force_kill(self):
        os.killpg(self.pgpid, signal.SIGTERM)

    def is_alive(self):
        # The leader of the group is the shell started by NPF: once killed, it stays in its group as a zombie until it
        # is reaped, which the executor may not do if it returned when the test was terminated. So do its orphans when
        # NPF adopts them (as PID 1 of a container).
        try:
            while os.waitpid(-self.pgpid, os.WNOHANG)[0]:
                pass
        except ChildProcessError:
            pass
        try:
            os.killpg(self.pgpid, 0)
        except PermissionError:
            return True
        except ProcessLookupError:
            return False
        return True

class LocalExecutor(Executor):
    @staticmethod
    def _absolute_paths(paths, options):
        """Relative paths (such as the build folder of a repository given as local/some/folder) are relative to the folder
        NPF was started in, while scripts run in a folder of the experiment."""
        try:
            base = npf.globals.cwd_path(options)
        except AttributeError:
            base = None
        if not base:
            base = str(Path(os.getcwd()).parent)
        return [p if os.path.isabs(p) else os.path.join(base, p) for p in paths or []]

    def __init__(self):
        super().__init__()

    def exec(self, cmd : str, bin_paths : List[str]=[],
             queue: Queue = None, options = None,
             stdin = None, timeout = None, sudo = False,
             testdir=None, event=None, title=None, env = {}, virt="" , nokill=False
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

        if not title:
            title = "local"
        env = env.copy()
        # Only NPF's variables are exported in the script: exporting the inherited environment would reset PATH and
        # hide the bin folders of the repositories added below
        env_str = self.get_env_str(env, options)
        cmd = env_str + cmd
        env.update(os.environ)
        bin_path = ':'.join(self._absolute_paths(bin_paths, options))
        if bin_paths:
            if not sudo:
                env["PATH"] = bin_path + ":" + env["PATH"]
            else:
                cmd = 'export PATH=' + bin_path + ':$PATH\n' + cmd

        if options is not None and options.show_cmd:
            print("Executing (PATH+=%s) :\n%s" % (bin_path, cmd.strip()))

        if sudo and pwd.getpwuid(os.getuid()).pw_name != "root":
            cmd = "sudo -E " + virt + "  bash -c '"+ cmd.replace("'", "'\"'\"'") + "'";
        else:
            cmd = virt + " bash -c '"+ cmd.replace("'", "'\"'\"'") + "'";

        return self._run(cmd, env, queue, options, timeout, event, title)

    def _make_killer(self, pgpid):
        return LocalKiller(pgpid)

    def _run(self, cmd, env, queue, options, timeout, event, title, make_killer=None):
        """Runs a shell command line, streams its output and returns pid, stdout, stderr, return code.
        Shared with executors that wrap the command (eg docker exec)."""
        make_killer = make_killer or self._make_killer
        outputs = ['', '']

        # stdout is a terminal, so programs flush it at each line instead of when their buffer is full, and EVENTs are
        # seen when printed. It is not the controlling terminal of the script (a new session that does not open it):
        # sudo still cannot ask for a password, and stdin and stderr stay pipes. NPF keeps the terminal open until the
        # script ended and its output was read: once all its processes closed it, macOS drops what was not read yet.
        master, slave = pty.openpty()
        attrs = termios.tcgetattr(slave)
        attrs[1] &= ~termios.OPOST  # "\n" stays "\n"
        termios.tcsetattr(slave, termios.TCSANOW, attrs)
        try:
            p = Popen(cmd,
                      stdin=PIPE, stdout=slave, stderr=PIPE,
                      shell=True, preexec_fn=os.setsid,
                      env=env)
        except BaseException:
            os.close(master)
            os.close(slave)
            raise

        select_set = select.poll()
        select_set.register(master,select.POLLIN)
        select_set.register(p.stderr,select.POLLIN)
        os.set_blocking(master, False)
        os.set_blocking(p.stderr.fileno(), False)
        pid = p.pid
        pgpid = os.getpgid(pid)
        flushing = False

        step = 0.2
        start = time.time()
        killer = make_killer(pgpid)
        if queue:
            queue.put(killer)
        try:
            while True:
                select_set.poll(step * 1000)
                for ichannel, fd in enumerate([master, p.stderr.fileno()]):
                    for line in self._read_lines(fd):
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
                    if timeout < time.time() - start:
                        raise TimeoutExpired(cmd, timeout)

            p.stdin.close()
            p.stderr.close()

            return pid, outputs[0], outputs[1], 0 if event and event.is_terminated() else p.returncode
        except TimeoutExpired:
            print("Test expired")
            p.terminate()
            p.kill()
            killer.kill()
            try:
                os.killpg(pgpid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
            p.stdin.close()
            p.stderr.close()

            return 0, outputs[0], outputs[1], p.returncode
        except KeyboardInterrupt:
            killer.kill()

            return -1, outputs[0], outputs[1], p.returncode
        finally:
            os.close(master)
            os.close(slave)

    @staticmethod
    def _read_lines(fd):
        """Reads what fd has. :return: its lines, the last one may not be finished"""
        data = b''
        # Bounded, so a script printing without a pause does not keep the loop from checking its end and timeout
        while len(data) < 1 << 20:
            try:
                chunk = os.read(fd, 65536)
            except BlockingIOError:
                break
            except OSError:
                # EIO on Linux if the terminal is closed. readlines() would drop the lines it already read.
                break
            if not chunk:
                break
            data += chunk
        lines = data.split(b'\n')
        return [l + b'\n' for l in lines[:-1]] + ([lines[-1]] if lines[-1] else [])

    def writeFile(self,filename,path_to_root,content,sudo=False):
        f = open(filename, "w")
        f.write(content)
        f.close()
        return True
