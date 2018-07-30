import multiprocessing
import os
import time
from multiprocessing import Queue
from typing import List
import paramiko
from .executor import Executor
from ..eventbus import EventBus
from paramiko.buffered_pipe import PipeTimeout
import socket
from colorama import Fore, Back, Style

class SSHExecutor(Executor):

    def __init__(self, user, addr, path):
        self.user = user
        self.addr = addr
        self.path = path

        #Executor should not make any connection in init as parameters can be overwritten afterward

    def get_connection(self):
        import paramiko
        ssh = paramiko.SSHClient()
        ssh.load_system_host_keys()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(self.addr, username=self.user)
        return ssh

    def exec(self, cmd, bin_paths : List[str] = None, queue: Queue = None, options = None, stdin = None, timeout=None, sudo=False, testdir=None, event=None, title=None):
        if not title:
            title = self.addr
        if not event:
            event = EventBus()
        path_list = [p if os.path.isabs(p) else self.path+'/'+p for p in (bin_paths if bin_paths is not None else [])]
        if options and options.show_cmd:
            print("Executing on %s%s (PATH+=%s) :\n%s" % (self.addr,(' with sudo' if sudo and self.user != "root" else ''),':'.join(path_list), cmd.strip()))

        pre = 'cd '+ self.path + '\n'
        if path_list:
            path_cmd = 'export PATH="%s:$PATH"\n' % (':'.join(path_list))
        else:
            path_cmd = ''

        if sudo and self.user != "root":
            cmd = "sudo -E bash -c '"+path_cmd + cmd.replace("'", "\\'") + "'";
        else:
            pre = path_cmd + pre

        try:
            ssh = self.get_connection()


            ssh_stdin, ssh_stdout, ssh_stderr = ssh.exec_command(pre + cmd,timeout=timeout, get_pty=True)

            if stdin is not None:
                ssh_stdin.write(stdin)

            out=''
            err=''
            pid = os.getpid()
            step = 0.2
            ssh_stdout.channel.setblocking(False)
            while not event.is_terminated() and not ssh_stdout.channel.exit_status_ready():
                try:
                    line = None
                    while ssh_stdout.channel.recv_ready():
                         line = ssh_stdout.readline()
                         if options and options.show_full:
                             print(Fore.GREEN + title + Style.RESET_ALL + ' ' + line, end='')
                         self.searchEvent(line, event)
                         out = out + line
                    else:
                        event.wait_for_termination(step)
                        if timeout is not None:
                            timeout -= step
                except PipeTimeout:
                    print("PipeT")
                    pass
                except socket.timeout:
                    print("SocketT")
                    event.wait_for_termination(step)
                    if timeout is not None:
                        timeout -= step
                except KeyboardInterrupt:
                    event.terminate()
                    return -1, out, err
                if timeout is not None:
                    if timeout < 0:
                        print("TIMEOUT")
                        event.terminate()
                        pid = 0
                        break
            if event.is_terminated():
                if not ssh_stdin.channel.closed:
                    ssh_stdin.channel.send(chr(3))
                    i=0
                    ssh_stdout.channel.status_event.wait(timeout=1)
                ret = 0 #Ignore return code because we kill it before completion.
                ssh.close()
            else:
                ret = ssh_stdout.channel.recv_exit_status()

            for line in ssh_stdout.readlines():
                if options and options.show_full:
                    print(Fore.GREEN + title + Style.RESET_ALL + ' ' + line, end='')
                self.searchEvent(line, event)
                out = out + line
            err = ssh_stderr.read().decode()


            return pid,out,err,ret
        except paramiko.ssh_exception.SSHException as e:
            print("Error while connecting to %s", self.addr)
            raise e

        #
        # try:
        #     s_output, s_err = [x.decode() for x in
        #                        p.communicate(stdin, timeout=timeout)]
        #     p.stdin.close()
        #     p.stderr.close()
        #     p.stdout.close()
        #     return pid, s_output, s_err, p.returncode
        # except TimeoutExpired:
        #     print("Test expired")
        #     p.terminate()
        #     p.kill()
        #     os.killpg(pgpid, signal.SIGKILL)
        #     os.killpg(pgpid, signal.SIGTERM)
        #     s_output, s_err = [x.decode() for x in p.communicate()]
        #     print(s_output)
        #     print(s_err)
        #     p.stdin.close()
        #     p.stderr.close()
        #     p.stdout.close()
        #     return 0, s_output, s_err, p.returncode
        # except KeyboardInterrupt:
        #     os.killpg(pgpid, signal.SIGKILL)
        #     return -1, s_output, s_err, p.returncode

    def writeFile(self,filename,path_to_root,content):
        f = open(filename, "w")
        f.write(content)
        f.close()
#        if self.user:
#            os.system("scp %s %s@%s:%s/" % (filename, self.user,self.addr,self.path))
#        else:
#            os.system("scp %s %s:%s/" % (filename, self.addr,self.path))
        try:
            with paramiko.SSHClient() as ssh:
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.load_system_host_keys()
                try:
                    ssh.connect(self.addr, 22, username=self.user)
                except Exception as e:
                    print("Cannot connect to %s with username %s" % (self.addr,self.user))
                    raise e

                transport = ssh.get_transport()
                with transport.open_channel(kind='session') as channel:
                    channel.exec_command('mkdir -p %s/%s' % (self.path, path_to_root))
                    if channel.recv_exit_status() != 0:
                        return False
                with transport.open_channel(kind='session') as channel:
                    channel.exec_command('cat > %s/%s/%s' % (self.path,path_to_root,filename))
                    channel.sendall(content)
                    channel.shutdown_write()
                    return channel.recv_exit_status() == 0
        except paramiko.ssh_exception.SSHException as e:
            print("Error while connecting to %s", self.addr)
            raise e
