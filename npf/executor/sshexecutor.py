import multiprocessing
import os,errno
import time
from multiprocessing import Queue
from typing import List
import paramiko
from .executor import Executor
from ..eventbus import EventBus
from paramiko.buffered_pipe import PipeTimeout
import socket

class SSHExecutor(Executor):

    def __init__(self, user, addr, path, port):
        super().__init__()
        self.user = user
        self.addr = addr
        self.path = path
        self.port = port
        self.ssh = False
        #Executor should not make any connection in init as parameters can be overwritten afterward

    def get_connection(self, cache=True):
        import paramiko
        if cache and self.ssh:
            return self.ssh
        ssh = paramiko.SSHClient()
        ssh.load_system_host_keys()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(self.addr, username=self.user, port=self.port)
        if cache:
            self.ssh = ssh
        return ssh


    def exec(self, cmd, bin_paths : List[str] = None, queue: Queue = None, options = None, stdin = None, timeout=None, sudo=False, testdir=None, event=None, title=None, env={}, virt = "", raw = False):
        if not title:
            title = self.addr
        if not event:
            event = EventBus()
        path_list = [p if os.path.isabs(p) else self.path+'/'+p for p in (bin_paths if bin_paths is not None else [])]
        if options and options.show_cmd:
            print("Executing on %s%s (PATH+=%s) :\n%s" % (self.addr,(' with sudo' if sudo and self.user != "root" else ''),':'.join(path_list) + (("NS:"  + virt) if virt else ""), cmd.strip()))

        pre = 'cd '+ self.path + ';'

        if self.path:
            env['NPF_ROOT'] = self.path

        for k,v in env.items():
            if v is not None:
                pre += 'export ' + k + '='+v+'\n'
        if path_list:
            path_cmd = 'export PATH="%s:$PATH"\n' % (':'.join(path_list))
        else:
            path_cmd = ''

        if raw:
            unbuffer = ""
        else:
            unbuffer = "unbuffer"
            if stdin is not None:
                unbuffer = unbuffer + " -p"

        if sudo and self.user != "root":
            cmd = "mkdir -p "+testdir+" && sudo -E " + virt +" "+unbuffer+" bash -c '"+path_cmd + cmd.replace("'", "'\"'\"'") + "'";
        else:
            cmd = virt +" "+unbuffer+" bash -c '"+path_cmd + cmd.replace("'", "'\"'\"'") + "'";
            #pre = path_cmd + pre

        try:
            ssh = self.get_connection(cache=False)

            ssh_stdin, ssh_stdout, ssh_stderr = ssh.exec_command("echo $$;"+ pre + cmd,timeout=timeout, get_pty=True)
            rpid = int(ssh_stdout.readline())
            if stdin is not None:
                ssh_stdin.write(stdin)
            channels = [ssh_stdout, ssh_stderr]
            output = ['','']

            pid = os.getpid()
            step = 0.2
            for channel in channels:
                channel.channel.setblocking(False)

            while not event.is_terminated() and not ssh_stdout.channel.exit_status_ready():
                try:
                    line = None
                    while ssh_stdout.channel.recv_ready() or ssh_stderr.channel.recv_ready():
                        for ichannel,channel in enumerate(channels[:1]):
                            if channel.channel.recv_ready():
                                try:
                                    line = channel.readline()
                                    if options and options.show_full:
                                        self._print(title, line, False)
                                    self.searchEvent(line, event)
                                    output[ichannel] += line
                                except UnicodeDecodeError:
                                    print("Could not decode SSH input")
                    else:
                        event.wait_for_termination(step)
                        if timeout is not None:
                            timeout -= step
                except PipeTimeout:
                    pass
                except socket.timeout:
                    self._print(title, "Interrupted by timeout", True)
                    event.wait_for_termination(step)
                    if timeout is not None:
                        timeout -= step
                except KeyboardInterrupt:
                    event.terminate()
                    return -1, out, err
                if timeout is not None:
                    if timeout < 0:
                        event.terminate()
                        pid = 0
                        break
            if event.is_terminated():
                if not ssh_stdin.channel.closed:
                    ssh_stdin.channel.send(chr(3))
                    ssh.exec_command("kill "+str(rpid))
#                   unneeded ssh.exec_command("kill $(ps -s  "+str(rpid)+" -o pid=)" )
                    i=0
                    ssh_stdout.channel.status_event.wait(timeout=1)

                ret = 0 #Ignore return code because we kill it before completion.
                ssh.close()
            else:
                ret = ssh_stdout.channel.recv_exit_status()

            for ichannel,channel in enumerate(channels):
                for line in channel.readlines():
                    if options and options.show_full:
                        self._print(title, line, False)
                    self.searchEvent(line, event)
                    output[ichannel] += line

            return pid,output[0], output[1],ret
        except socket.gaierror as e:
            print("Error while connecting to %s" % self.addr)
            print(e)
            return 0,'','',-1
        except paramiko.ssh_exception.SSHException as e:
            print("Error while connecting to %s" % self.addr)
            print(e)
            return 0,'','',-1

    def writeFile(self,filename,path_to_root,content):
        f = open(filename, "w")
        f.write(content)
        f.close()

        try:
            with paramiko.SSHClient() as ssh:
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.load_system_host_keys()
                try:
                    ssh = self.get_connection()
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
            print("Error while connecting to %s" % self.addr)
            raise e

    def sendFolder(self, path, local=None):
        try:
            with paramiko.SSHClient() as ssh:
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.load_system_host_keys()
                try:
                    ssh = self.get_connection()
                except Exception as e:
                    print("Cannot connect to %s with username %s" % (self.addr,self.user))
                    raise e

                transport = ssh.get_transport()

                sftp = paramiko.SFTPClient.from_transport(transport)

                ignored = ['.git', '.vimhistory']
                def _send(path):
                    total = 0
                    rlist = sftp.listdir(self.path + path)
                    lpath = lpath if not local else local + os.sep + path
                    for entry in os.scandir(lpath):
                        if entry.is_file():
                            remote = self.path + path + '/' + entry.name
                            if not entry.name in rlist or entry.stat().st_size != sftp.stat(remote).st_size:
                                try:
                                    es = entry.stat()
                                    sftp.put(lpath + '/' + entry.name, remote)
                                    sftp.chmod(remote, es.st_mode)
                                    total += es.st_size
                                except FileNotFoundError:
                                    raise(Exception("Could not send %s to %s"  % (path + '/' + entry.name, remote)))
                        else:
                            if entry.name in ignored:
                                continue
                            if entry.name not in rlist:
                                sftp.mkdir(self.path + path + '/' + entry.name, mode=0o777 )
                                total += _send(path +'/'+entry.name + '/')
                    return total
                curpath = ''
                total = 0
                for d in path.split('/'):
                    curpath = curpath + d + '/'
                    lcurpath = curpath if not local else local + os.sep + curpath
                    if not os.path.isdir(lcurpath):
                        remote = self.path + path
                        try:
                            sftp.stat(remote)
                        except IOError as e:
                            if e.errno is errno.ENOENT:
                                lpath = path if not local else local + os.sep + path
                                es = os.stat(lpath)
                                sftp.put(lpath, remote)
                                sftp.chmod(remote, es.st_mode)
                                total += es.st_size
                        finally:
                            sftp.close()
                        return total
                    try:
                        f = self.path + '/' + curpath
                        sftp.stat(f)
                    except FileNotFoundError:
                        try:
                            sftp.mkdir(f,mode=0o777)
                        except IOError as e:
                            print("Could not make folder %s" % f)
                            raise e
                    except PermissionError as e:
                        print("Could not make folder %s" % f)
                        raise e


                total += _send(path)

                sftp.close()
                return total

        except paramiko.ssh_exception.SSHException as e:
            print("Error while connecting to %s" % self.addr)
            raise e
