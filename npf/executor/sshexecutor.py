import multiprocessing
import os,errno
import shlex
import threading
import time
from multiprocessing import Queue
from typing import List
import warnings
from cryptography.utils import CryptographyDeprecationWarning

import npf.globals
from npf.tests.eventbus import EventBus
with warnings.catch_warnings():
    warnings.filterwarnings('ignore', category=CryptographyDeprecationWarning)
    import paramiko
from .executor import Executor

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
        self.identityfile = None
        self.ssh_config = None
        # Scripts run in threads and share one connection, each in its own channel
        self._lock = threading.Lock()
        #Executor should not make any connection in init as parameters can be overwritten afterward

    def __del__(self):
        if self.ssh:
            self.ssh.close()

    def get_connection(self, cache=True):
        """The connection to the node, shared by all its scripts. With cache=False, a new one the caller closes."""
        if not cache:
            return self._connect()
        with self._lock:
            transport = self.ssh.get_transport() if self.ssh else None
            if not transport or not transport.is_active():
                if self.ssh:
                    self.ssh.close()
                self.ssh = self._connect()
                # Keeps it open through gateways and NATs while no script runs
                self.ssh.get_transport().set_keepalive(30)
            return self.ssh

    def _exec_command(self, cmd, pty=False):
        """Runs cmd in a new channel of the shared connection.

        :return: stdin, stdout, stderr, and the connection to close after the command when the shared one could not
                 take another channel (sshd allows MaxSessions channels per connection, 10 by default), else None
        """
        shared = self.get_connection()
        try:
            return shared.exec_command(cmd, get_pty=pty) + (None,)
        except paramiko.ssh_exception.SSHException:
            # A refused channel is not always a ChannelException: threads opening channels at the same time share
            # the error of the transport
            if not shared.get_transport().is_active():
                # The connection died (e.g. the node rebooted), get_connection makes a new one
                return self.get_connection().exec_command(cmd, get_pty=pty) + (None,)
            own = self._connect()
            return own.exec_command(cmd, get_pty=pty) + (own,)

    def _connect(self):
        import paramiko
        ssh = paramiko.SSHClient()

        cfg = {'hostname': self.addr, 'username': self.user, 'port': self.port, 'identityfile': self.identityfile}

        #Inspired by https://gist.github.com/acdha/6064215
        ssh_config=None
        if npf.globals.options.sshconfig:
            ssh_config = paramiko.SSHConfig()
            user_config_file = os.path.expanduser("~/.ssh/config")
            if os.path.exists(user_config_file):
                with open(user_config_file) as f:
                    ssh_config.parse(f)

            user_config = ssh_config.lookup(cfg['hostname'])
            for k in ('hostname', 'username', 'port', 'identityfile'):
                if k in user_config:
                    cfg[k] = user_config[k]

            if 'proxycommand' in user_config:
                # Through a shell, as ssh does: paramiko runs it directly, without $(...), pipes or ~
                cfg['sock'] = paramiko.ProxyCommand(shlex.join(["/bin/sh", "-c", user_config['proxycommand']]))

            #ssh.load_system_host_keys()
            if cfg["identityfile"]:
                try:
                    found=False
                    for key_class in [paramiko.RSAKey, paramiko.DSSKey, paramiko.ECDSAKey, paramiko.Ed25519Key]:
                        keys = cfg["identityfile"]
                        if not type(keys) is list:
                            keys = [keys]
                        for key in keys:
                            try:
                                k = key_class.from_private_key_file(key)
                                found=True
                                break
                            except paramiko.ssh_exception.SSHException as e:
                                continue
                        if found:
                            break
                    if not found:
                        raise paramiko.ssh_exception.SSHException("Could not load private key from %s" % cfg["identityfile"])
                except IOError as e:
                    print("Could not load host keys from %s" % cfg["identityfile"])
                    raise e
        self.ssh_config = cfg
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(cfg["hostname"], username=cfg["username"], port=cfg["port"],sock=cfg['sock'] if "sock" in cfg else None, pkey=k if cfg["identityfile"] else None)
        return ssh


    def exec(self, cmd, bin_paths : List[str] = None,
             queue: Queue = None, options = None,
             stdin = None, timeout=None, sudo=False, testdir=None,
             event=None, title=None, env={}, virt = "", raw = False, nokill = False):
        if testdir:
            cmd = "mkdir -p " + testdir + " && cd " + testdir + ";\n" + cmd;
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
        pre = 'cd '+ self.path + ';\n'

        env_str = self.get_env_str(env, options)
        if path_list:
            path_cmd = 'export PATH="%s:$PATH"\n' % (':'.join(path_list))
        else:
            path_cmd = ''

        cmd = env_str + cmd
        if sudo and self.user != "root":
            # -n: in the terminal of the script, sudo would wait for a password instead of failing
            cmd = "sudo -n -E  mkdir -p "+testdir+" && sudo -n -E " + virt + " bash -c '"+path_cmd + cmd.replace("'", "'\"'\"'") + "'";
        else:
            cmd = virt + " bash -c '" + path_cmd + cmd.replace("'", "'\"'\"'") + "'";

        own = None
        ssh_stdout = None
        try:
            #First echo the pid of the shell, so it can be recovered and killed in case of kill from another script
            #Then launch the pre-command (goes to the right folder)
            #Then the user command, wrapped with sudo and/or bash if needed
            final_command = "echo $$;"+ pre + cmd + " ; retval=$? ; echo '' ; exit $retval"
            # In a terminal, programs flush their output at each line instead of when their buffer is full, so EVENTs
            # are seen when printed. Its echo is disabled before stdin is sent, once the pid is read. stderr goes
            # to the same terminal.
            pty = not raw
            if pty:
                final_command = "stty -echo 2>/dev/null; " + final_command
            ssh_stdin, ssh_stdout, ssh_stderr, own = self._exec_command(final_command, pty)
            if stdin is not None and not pty:
                ssh_stdin.write(stdin)
            channels = [ssh_stdout, ssh_stderr]
            output = ['','']
            buffers = ['','']
            rpid = -1
            # EVENTs of the current partial line already posted, see below
            partial_events = 0
            pid = os.getpid()
            step = 0.2
            #for channel in channels:
            #   channel.channel.setblocking(False)

            while ((nokill or not event.is_terminated()) and not ssh_stdout.channel.exit_status_ready()) or (ssh_stdout.channel.recv_ready() or ssh_stderr.channel.recv_ready()):
                try:
                    line = None
                    received = False
                    for ichannel,channel in enumerate(channels):
                        chan = channel.channel
                        ichannel = 0
                        if chan.recv_ready():
                            received = True
                            try:
                                data = chan.recv(1024)
                                buffers[ichannel] = buffers[ichannel] + data.decode("utf-8")
                                while "\n" in buffers[ichannel]:
                                    p = buffers[ichannel].index("\n")
                                    line = buffers[ichannel][:p+1]
                                    buffers[ichannel] = buffers[ichannel][p+1:]
                                    if rpid == -1:
                                        rpid = int(line)
                                        if stdin is not None and pty:
                                            ssh_stdin.write(stdin)
                                    else:
                                        if options and not options.quiet:
                                            self._print(title, line, False)
                                        self.searchEvent(line, event, skip=partial_events)
                                        partial_events = 0
                                        output[ichannel] += line
                            except UnicodeDecodeError:
                                        print("Could not decode SSH input")
                            except Exception as e:
                                print("Error")
                                print(e)
                                raise(e)

                    else:
                        # A line printed without its newline (e.g. printf "EVENT ready"), once the output pauses
                        if not received and buffers[0] and rpid != -1:
                            partial_events = self.searchEvent(buffers[0], event, skip=partial_events)
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
                    return -1, output[0], output[1], 0
                if timeout is not None:
                    if timeout < 0:
                        event.terminate()
                        pid = 0
                        break
                if not nokill and event.is_terminated():
                    print("Terminated, so killing if", queue)
                    if not ssh_stdin.channel.closed:

                        if options and options.debug:
                            print("[DEBUG] %s: Sending SIGKILL to %d" % (title,rpid))
                        ssh_stdin.channel.send(chr(3))
                    # sshd starts the shell in a new session: its pid is the process group of the whole script
                    # (and "kill -1", before the pid is known, would signal every process of the user)
                    if rpid > 1:
                        k = "kill -- -%d 2>/dev/null; kill %d 2>/dev/null; true" % (rpid, rpid)
                        if sudo and self.user != "root":
                            k = "sudo -n sh -c '%s'" % k
                        _, k_out, _, k_own = self._exec_command(k)
                        k_out.channel.status_event.wait(timeout=5)
                        self._close(k_out, k_own)
                    ssh_stdout.channel.status_event.wait(timeout=1)
                # end of loop

            if event.is_terminated():
                ret = 0 #Ignore return code because we kill it before completion.
            else:
                ret = ssh_stdout.channel.recv_exit_status()
            return pid,output[0], output[1],ret
        except socket.gaierror as e:
            print("Error while connecting to %s" % self.addr)
            print(e)
            return 0,'','',-1
        except paramiko.ssh_exception.SSHException as e:
            print("Error while connecting to %s" % self.addr)
            print(e)
            return 0,'','',-1
        finally:
            self._close(ssh_stdout, own)

    @staticmethod
    def _close(stdout, own):
        """Closes the channel of a command, and its connection if it is not the shared one"""
        if stdout is not None:
            stdout.channel.close()
        if own is not None:
            own.close()

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
