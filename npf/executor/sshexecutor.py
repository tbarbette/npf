import multiprocessing
import os,errno
import time
from multiprocessing import Queue
from typing import List
import warnings
from cryptography.utils import CryptographyDeprecationWarning
with warnings.catch_warnings():
    warnings.filterwarnings('ignore', category=CryptographyDeprecationWarning)
    import paramiko
from .executor import Executor
from ..eventbus import EventBus
from .. import npf
from paramiko.buffered_pipe import PipeTimeout
import socket
import stat

class SSHExecutor(Executor):

    def __init__(self, user, addr, path, port):
        super().__init__()
        self.user = user
        self.addr = addr
        if path[-1] == '/':
            self.path = path
        else:
            self.path = path + '/'
        self.port = port
        self.ssh = False
        #Executor should not make any connection in init as parameters can be overwritten afterward

    def __del__(self):
        if self.ssh:
            self.ssh.close()

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
        else:
            title = self.addr + ' - ' + title
        if not event:
            event = EventBus()
        if bin_paths is None:
            bin_paths = []
        path_list = [p if os.path.isabs(p) else os.path.join(self.path, p) for p in bin_paths]
        if options and options.show_cmd:
            print("Executing on %s%s (PATH+=%s) :\n%s" % (self.addr,(' with sudo' if sudo and self.user != "root" else ''),':'.join(path_list) + (("NS:"  + virt) if virt else ""), cmd.strip()))

        # The pre-command goes into the test folder
        pre = 'cd '+ self.path + ';'

        if self.path:
            env['NPF_ROOT'] = self.path
            env['NPF_CWD_PATH'] = os.path.relpath(npf.cwd_path(),self.path)
            env['NPF_EXPERIMENT_PATH'] = '../' + os.path.relpath(npf.experiment_path(), self.path)
            env['NPF_ROOT_PATH'] = '../' + os.path.relpath(npf.npf_root_path(), self.path)

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
            cmd = virt + " " + unbuffer +" bash -c '" + path_cmd + cmd.replace("'", "'\"'\"'") + "'";

        ssh = None
        try:
            ssh = self.get_connection(cache=False)

            #First echo the pid of the shell, so it can be recovered and killed in case of kill from another script
            #Then launch the pre-command (goes to the right folder)
            #Then the user command, wrapped with sudo and/or bash if needed
            ssh_stdin, ssh_stdout, ssh_stderr = ssh.exec_command("echo $$;"+ pre + cmd + " ; echo '' ;")
            if stdin is not None:
                ssh_stdin.write(stdin)
            channels = [ssh_stdout, ssh_stderr]
            output = ['','']
            buffers = ['','']
            rpid = -1
            pid = os.getpid()
            step = 0.2
            #for channel in channels:
            #   channel.channel.setblocking(False)

            while (not event.is_terminated() and not ssh_stdout.channel.exit_status_ready()) or (ssh_stdout.channel.recv_ready() or ssh_stderr.channel.recv_ready()):
                try:
                    line = None
                    for ichannel,channel in enumerate(channels):
                        chan = channel.channel
                        ichannel = 0
                        if chan.recv_ready():
                            try:
                                data = chan.recv(1024)
                                buffers[ichannel] = buffers[ichannel] + data.decode("utf-8")
                                while "\n" in buffers[ichannel]:
                                    p = buffers[ichannel].index("\n")
                                    line = buffers[ichannel][:p+1]
                                    buffers[ichannel] = buffers[ichannel][p+1:]
                                    if rpid == -1:
                                        rpid = int(line)
                                    else:
                                        if options and not options.quiet:
                                            self._print(title, line, False)
                                        self.searchEvent(line, event)
                                        output[ichannel] += line
                                    if buffers[ichannel]:
                                        self.searchEvent(buffers[ichannel], event)
                            except UnicodeDecodeError:
                                        print("Could not decode SSH input")
                            except Exception as e:
                                print("Error")
                                print(e)
                                raise(e)

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
                    ssh.close()
                    return -1, out, err, -1
                if timeout is not None:
                    if timeout < 0:
                        event.terminate()
                        pid = 0
                        break
                if event.is_terminated():
                    if not ssh_stdin.channel.closed:

                        if options and options.debug:
                            print("[DEBUG] %s: Sending SIGKILL to %d" % (title,rpid))
                        ssh_stdin.channel.send(chr(3))
                    ssh.exec_command("kill "+str(rpid))
#                   unneeded ssh.exec_command("kill $(ps -s  "+str(rpid)+" -o pid=)" )
                    i=0
                    ssh_stdout.channel.status_event.wait(timeout=1)
                # end of loop

            if event.is_terminated():
                ret = 0 #Ignore return code because we kill it before completion.
            else:
                ret = ssh_stdout.channel.recv_exit_status()
            ssh.close()
            ssh=None


            return pid,output[0], output[1],ret
        except socket.gaierror as e:
            print("Error while connecting to %s" % self.addr)
            print(e)
            if ssh:
                ssh.close()
            return 0,'','',-1
        except paramiko.ssh_exception.SSHException as e:
            print("Error while connecting to %s" % self.addr)
            print(e)
            if ssh:
                    ssh.close()
            return 0,'','',-1

    def writeFile(self,filename,path_to_root,content,sudo=False):
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
                    channel.exec_command(('sudo ' if sudo else '') + 'mkdir -p %s/%s' % (self.path, path_to_root))
                    if channel.recv_exit_status() != 0:
                        print("Could not create folder %s/%s!" % (self.path, path_to_root))
                        return False
                with transport.open_channel(kind='session') as channel:
                    channel.exec_command('cat - | ' + ('sudo ' if sudo else '') + 'tee %s/%s/%s &> /dev/null' % (self.path,path_to_root,filename))
                    channel.sendall(content)
                    channel.shutdown_write()
                    return channel.recv_exit_status() == 0
        except paramiko.ssh_exception.SSHException as e:
            print("Error while connecting to %s" % self.addr)
            raise e

    def sendFolder(self, path, local = None):
        sftp = None
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
                    skipped = 0
                    try:
                        rlist = sftp.listdir(self.path + path)
                        lpath = path if not local else local + os.sep + path
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
                                        sftp.close()
                                        raise(Exception("Could not send %s to %s"  % (path + '/' + entry.name, remote)))
                                else:
                                    skipped += entry.stat().st_size
                            else:
                                if entry.name in ignored:
                                    continue
                                if entry.name not in rlist:
                                    sftp.mkdir(self.path + path + '/' + entry.name, mode=0o777 )
                                t, s = _send(path +'/'+entry.name + '/')
                                total += t
                                skipped += s
                        return total, skipped
                    except FileNotFoundError:
                        sftp.close()
                        raise FileNotFoundError("No such file : %s" % (self.path + os.sep + path))
                curpath = ''
                total = 0
                skipped = 0
                for d in path.split('/'):
                    curpath = curpath + d + '/'
                    lcurpath = curpath if not local else local + os.sep + curpath
                    if not os.path.isdir(lcurpath):
                        remote = self.path + path
                        try:
                            s = sftp.stat(remote)
                            skipped += s.st_size
                        except IOError as e:
                            if e.errno is errno.ENOENT:
                                lpath = path if not local else local + os.sep + path
                                es = os.stat(lpath)
                                if not es:
                                    raise FileNotFoundError("[Errno 2] No such local file %s in %s" % (lpath, os.getcwd()))
                                try:
                                    sftp.put(lpath, remote)
                                except PermissionError as e:
                                    raise PermissionError("[Errno 13] Permission denied when trying to send .access_test to the remote folder '%s' on %s. Do you have the rights?" % (os.path.dirname(remote), self.addr)) from None
                                except FileNotFoundError as e:
                                    raise FileNotFoundError("[Errno 2] No such remote folder on %s: %s, please create it" % (self.addr,os.path.dirname(remote))) from None
                                sftp.chmod(remote, es.st_mode)
                                total += es.st_size
                        finally:
                            sftp.close()
                        return total, skipped
                    try:
                        f = self.path + '/' + curpath
                        sftp.stat(f)
                    except FileNotFoundError:
                        try:
                            sftp.mkdir(f,mode=0o777)
                        except IOError as e:
                            sftp.close()
                            print("Could not make remote folder %s" % f)
                            raise e
                    except PermissionError as e:
                        sftp.close()
                        print("Could not make folder %s" % f)
                        raise e

                t, s = _send(path)
                total += t
                skipped += s

                sftp.close()
                return total, skipped

        except paramiko.ssh_exception.SSHException as e:
            print("Error while connecting to %s" % self.addr)
            if sftp:
                sftp.close()
            raise e


    def deleteFolder(self, path):
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

                fileattr = sftp.lstat(self.path + path)
                try:
                    if stat.S_ISDIR(fileattr.st_mode):
                        sftp.rmdir(self.path + path)
                    else:
                        sftp.remove(self.path + path)
                except FileNotFoundError:
                    raise FileNotFoundError("Could not find %s, unable to delete it..." % (self.path + path))
                sftp.close()

        except paramiko.ssh_exception.SSHException as e:
            print("Error while connecting to %s" % self.addr)
            raise e
