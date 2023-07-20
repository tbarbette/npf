import multiprocessing
import os
import sys
import threading
import time
import traceback
import random
import shutil
import datetime
import itertools
import string
from pathlib import Path
from queue import Empty
from typing import Tuple, Dict
import numpy as np
from npf.build import Build
from npf.node import NIC
from npf.section import *
from npf.npf import get_valid_filename
from npf.types.dataset import Run, Dataset
from npf.eventbus import EventBus
from .variable import get_bool
from decimal import *
from functools import reduce

from subprocess import PIPE, Popen, TimeoutExpired

class RemoteParameters:
    def __init__(self):
        self.default_role_map = None
        self.role = None
        self.delay = None
        self.executor = None
        self.bin_paths = None
        self.queue = None
        self.sudo = None
        self.autokill = None
        self.queue = None
        self.timeout = None
        self.options = None
        self.stdin = None
        self.commands = None
        self.testdir = None
        self.waitfor = None
        self.event = None
        self.title = None
        self.env = None
        self.virt = ""

    pass


def _parallel_exec(param: RemoteParameters):
    nodes = npf.nodes_for_role(param.role)
    executor = nodes[param.role_id].executor
    for wf in param.waitfor if type(param.waitfor) is list else [param.waitfor]:
        if wf is None:
            continue
        n=1
        #print("Waiting for %s" % wf)
        if wf[0].isdigit():
            n=int(wf[0])
            wf=wf[1:]
        for i in range(n):
            param.event.listen(wf)

    param.event.wait_for_termination(param.delay)
    if param.event.is_terminated():
        if param.options.debug:
                print("[DEBUG] Script %s killed before its execution" % param.name)
        return 1, 'Killed before execution', 'Killed before execution', 0, param.script
    pid, o, e, c = executor.exec(cmd=param.commands,
                                 stdin=param.stdin,
                                 timeout=param.timeout,
                                 bin_paths=param.bin_paths,
                                 queue=param.queue,
                                 options=param.options,
                                 sudo=param.sudo,
                                 testdir=param.testdir,
                                 event=param.event,
                                 title=param.name,
                                 env=param.env,
                                 virt=param.virt)

    if pid == 0:
        return False, o, e, c, param.script
    else:
        if param.autokill is not None:
            if param.options.debug:
                print("[DEBUG] Script %s finished, killing all other scripts" % param.name)
            param.event.c.acquire()
            param.autokill.value = param.autokill.value - 1
            v = param.autokill.value
            param.event.c.release()
            if v == 0:
                Test.killall(param.queue, param.event)
        elif pid == -1:
            #Keyboard interrupt
            if param.options.debug:
                print("[DEBUG] Script %s stopped through keyboard interrupt." % param.name)
            Test.killall(param.queue, param.event)
        else:
            if param.options.debug:
                print("[DEBUG] Script %s finished, autokill=false so it will not terminate the other scripts." % param.name)
        if pid == -1:
            return -1, o, e, c, param.script
        return True, o, e, c, param.script


class ScriptInitException(Exception):
    pass


class Test:
    __test__ = False

    def get_name(self):
        return self.filename

    def get_scripts(self) -> List[SectionScript]:
        return self.scripts

    def __init__(self, test_path, options, tags=None, role=None, inline=None):
        loc_path = npf.find_local(test_path)
        if os.path.exists(loc_path):
            test_path = loc_path
        else:
            loc_path = npf.find_local(test_path + '.npf')
            if not os.path.exists(loc_path):
                if os.path.exists(npf.find_local(test_path + '.test')):
                    print("WARNING: .test extension is deprecated, use .npf")
                    test_path = npf.find_local(test_path + '.test')
                else:
                    raise FileNotFoundError("Could not find test script %s (tried also with .npf and .test extensions, without success)" % test_path)
            else:
                test_path = loc_path

        self.sections = []
        self.files = []
        self.init_files = []
        self.late_variables = []
        self.scripts = []
        self.imports = []
        self.requirements = []
        self.sendfile = {}
        self.filename = os.path.basename(test_path)
        self.path = os.path.dirname(os.path.abspath(test_path))
        self.options = options
        self.tags = tags if tags else []
        self.role = role

        i = -1
        try:
            section = None
            f = open(test_path, 'r')
            for i, line in enumerate(f):
                if section is None or section.noparse is False:
                    line = re.sub(r'(^|[ ])//.*$', '', line)
                if line.startswith('#') and section is None:
                    print("Warning : comments now use // instead of #. This will be soon deprecated")
                    continue
                if line.strip() == '' and not section:
                    continue

                if line.startswith("%"):
                    #Allow to start a line with a % using %% to indicate it's not a section
                    if line[1] == '%':
                        section.content += line[1:]
                        continue
                    result = line[1:]
                    section = SectionFactory.build(self, result.strip())

                    if not section is SectionNull:
                        self.sections.append(section)
                elif section is None:
                    raise Exception("Bad syntax, file must start by a section. Line %d :\n%s" % (i, line))
                else:
                    section.content += line
            f.close()

            if not hasattr(self, "info"):
                self.info = Section("info")
                self.info.content = self.filename
                self.sections.append(self.info)

            if not hasattr(self, "stdin"):
                self.stdin = Section("stdin")
                self.sections.append(self.stdin)

            if not hasattr(self, "variables"):
                self.variables = SectionVariable()
                self.sections.append(self.variables)

            if not hasattr(self, "config"):
                self.config = SectionConfig()
                self.sections.append(self.config)

            for section in self.sections:
                section.finish(self)
        except Exception as e:
            if i == -1:
                raise Exception("An exception occured while accessing the file %s" % (test_path))
            else:
                raise Exception("An exception occured while parsing %s at line %d:\n%s" % (test_path, i, e.__str__()))

        # Check that all reference roles are defined
        known_roles = {'self', 'default'}.union(set(npf.roles.keys()))
        for script in self.get_scripts():
            known_roles.add(script.get_role())
        # for file in self.files:
        #            for nicref in re.finditer(Node.NICREF_REGEX, file.content, re.IGNORECASE):
        #                if nicref.group('role') not in known_roles:
        #                    raise Exception("Unknown role %s" % nicref.group('role'))

        # Create imports tests
        for imp in self.imports:
            from npf.module import Module
            imp.test = Module(imp.module, options, self, imp, self.tags, imp.get_role())
            if len(imp.test.variables.dynamics()) > 0:
                raise Exception("Imports cannot have dynamic variables. Their parents decides what's dynamic.")
            if 'as_init' in imp.params:
                for script in imp.test.scripts:
                    script.init = True
            if 'delay' in imp.params:
                delay = imp.params.setdefault('delay', 0)
                for script in imp.test.scripts:
                    if 'delay' in script.params:
                        script.params['delay'] = float(delay) + float(script.params['delay'])
                    else:
                        script.params['delay'] = float(delay)
                del imp.params['delay']
            if 'waitfor' in imp.params:
                for script in imp.test.scripts:
                    wf = imp.params['waitfor']
                    if type(wf) is not list:
                        wf=[wf]
                    if script.type == SectionScript.TYPE_SCRIPT:
                        if not 'waitfor' in script.params:
                            script.params['waitfor'] = wf
                        else:
                            if type(script.params['waitfor']) is not list:
                                script.params['waitfor'] = [script.params['waitfor']]
                            script.params['waitfor'].expand(wf)
                del imp.params['waitfor']
            if 'autokill' in imp.params:
                for script in imp.test.scripts:
                    if script.type == SectionScript.TYPE_SCRIPT:
                        script.params['autokill'] = imp.params['autokill']
                del imp.params['autokill']
            if imp.multi is not None:
                for script in imp.test.scripts:
                    if script.type == SectionScript.TYPE_SCRIPT or script.type == SectionScript.TYPE_INIT:
                        script.multi = imp.multi
            overriden_variables = {}
            for k, v in imp.params.items():
                overriden_variables[k] = VariableFactory.build(k, v)
            imp.test.variables.override_all(overriden_variables)
            if "require_tags" in imp.test.config.vlist:
                tags = imp.test.config.vlist["require_tags"].makeValues()
                if tags:
                    tags = reduce(list.__add__,map(lambda x:x.split(','), tags))

                if "import" in tags:
                    tags.remove("import")

                imp.test.config.vlist["require_tags"] = ListVariable(imp.test.config.vlist["require_tags"].name, tags)

            imp.test.config.override_all(self.config.vlist)
            self.config = imp.test.config
            if not imp.is_include:
                for script in imp.test.scripts:
                    if script.get_role():
                        raise Exception('Modules cannot have roles, their importer defines it')
                    script._role = imp.get_role()
                nsendfile = {}
                for role,fpaths in imp.test.sendfile.items():
                    if role and role != 'default':
                        raise Exception('Modules cannot have roles (sendfile has role %s), their importer defines it' % role)
                    nsendfile[imp.get_role()] = fpaths
                imp.test.sendfile = nsendfile

                if hasattr(imp.test, 'exit'):
                    imp.test.exit._role = imp.get_role()
            else: #is include
                self.variables.vlist.update(imp.test.variables.vlist)

    def build_deps(self, repo_under_test: List[Repository], v_internals={}, no_build=False, done=None):
        if done is None:
            done = set()
        # Check for dependencies
        deps = set()
        for script in self.get_scripts():
            deps = deps.union(script.get_deps())
        for dep in deps:
            if dep in [repo.reponame for repo in repo_under_test]:
                continue
            deprepo = Repository.get_instance(dep, self.options)
            if deprepo.url is None or deprepo.reponame in self.options.no_build_deps:
                continue
            if not deprepo.get_last_build().build(force_build=deprepo.reponame in self.options.force_build_deps):
                raise Exception("Could not build dependency %s" % dep)
        #Do the same for the imports
        for imp in self.imports:
            imp.test.build_deps(repo_under_test, v_internals, True, done=done)

        # Send dependencies for nfs=0 nodes
        toSend = set()
        for script in self.get_scripts():
            role = script.get_role()
            nodes = npf.nodes_for_role(role)
            for node in nodes:
              if not node.nfs:
                for repo in repo_under_test:
                    if repo.get_build_path() and not no_build:
                        toSend.add((repo.reponame,role,node, repo.get_build_path(), repo.get_remote_build_path(node)))
                for dep in script.get_deps():
                    deprepo = Repository.get_instance(dep, self.options)

                    toSend.add((deprepo.reponame,role,node,deprepo.get_build_path(), deprepo.get_remote_build_path(node)))
        for repo,role,node,bp,rbp in toSend.difference(done):
            print("Sending software %s to %s... " % (repo, role), end ='')
            try:

                #We have to find the local path from which the remote start, so we can advance in the folder at the same point
                local = os.path.normpath(bp)
                r = os.path.normpath(rbp)
                while os.path.basename(local) == os.path.basename(r):
                    local = os.path.dirname(os.path.normpath(local))
                    r = os.path.dirname(os.path.normpath(r))
                t,s = node.executor.sendFolder(rbp,local)
            except Exception as e:
                print ("While sending %s (to folder %s) on node %s= " %  (bp, rbp, node.addr))
                raise e
            if t > 0 and s > 0:
                print("%d bytes sent / %d bytes already up to date." % (t,s))
            elif t > 0 and s == 0:
                print("%d bytes sent." % (t))
            else:
                print("Already up to date (%d bytes) !" % s)

        done.update(toSend)

        st = dict([(f, v.makeValues()[0]) for f, v in self.variables.statics().items()])
        st.update(v_internals)

        for late_variables in self.get_late_variables():
            st.update(late_variables.execute(st, self, fail=False))

        L = [imp.test.sendfile for imp in self.imports]
        for role, fpaths in itertools.chain(self.sendfile.items(), {k: v for d in L for k, v in d.items()}.items()):
            nodes = npf.nodes_for_role(role)
            for node in nodes:
              if not node.nfs:
                for fpath in fpaths:
                    fpath = SectionVariable.replace_variables(st, fpath, role, self_node=node,
                                                              default_role_map=self.config.get_dict("default_role_map"))
#                    if not os.path.isabs(fpath):
#                        fpath = './npf/' + fpath
                    fpath = os.path.relpath(fpath)
                    print("Sending files %s to %s... " % (fpath, role), end = '')
                    t = node.executor.sendFolder(fpath)
                    if (t[0] > 0):
                        print("%d bytes sent." % t)
                    else:
                        print("Already up to date !")


        return True

    def test_tags(self):
        missings = []
        for tag in self.config.get_list("require_tags"):
            if not tag in self.tags:
                missings.append(tag)
        return missings

    def build_file_list(self, v, self_role=None, files=None) -> List[Tuple[str, str, str]]:
        create_list = []
        if files is None:
            files = self.files
        for s in files:
            role = s.get_role() if s.get_role() else self_role
            v["NPF_NODE_MAX"] = len(npf.nodes_for_role(role))
            if not s.noparse:
                s.filename = SectionVariable.replace_variables(v, s.filename, role, default_role_map = self.config.get_dict("default_role_map"))
                p = SectionVariable.replace_variables(v, s.content, role,default_role_map = self.config.get_dict("default_role_map"))
            else:
                p = s.content
            create_list.append((s.filename, p, role))
        return create_list

    def create_files(self, file_list, path_to_root):
        unique_list = {}
        for filename, p, role in file_list:
            if filename in unique_list:
                if unique_list[filename + (role if role else '')][1] != p:
                    raise Exception(
                        "File name conflict ! Some of your scripts try to create some file with the same name but "
                        "different content (%s) !" % filename)
            else:
                unique_list[filename + (role if role else '')] = (filename, p, role)

        for whatever, (filename, p, role) in unique_list.items():
            if self.options.show_files:
                print("File %s:" % filename)
                print(p.strip())
            for node in npf.nodes_for_role(role):
                if not node.executor.writeFile(filename, path_to_root, p):
                    print("Re-trying with sudo...")
                    if not node.executor.writeFile(filename, path_to_root, p, sudo=True):
                        raise Exception("Could not create file %s on %s" % (filename, node.name))

    def test_require(self, v, build):
        for require in self.requirements + list(itertools.chain.from_iterable([imp.test.requirements for imp in self.imports])):
            p = SectionVariable.replace_variables(v, require.content, require.role(),
                                                  self.config.get_dict("default_role_map"))
            pid, output, err, returncode = npf.executor(require.role(), self.config.get_dict("default_role_map")).exec(
                cmd=p, bin_paths=[build.get_local_bin_folder()], options=self.options, event=None, testdir=None)
            if returncode != 0:
                return False, output, err
            continue
        return True, '', ''

    def cleanup(self):
        for s in self.files:
          try:
            path = Path(s.filename)
            if path.is_file():
                path.unlink()
          except:
            print("Could not cleanup file %s" % s.filename)

    @staticmethod
    def killall(queue, event):
        event.terminate()
        while not queue.empty():
            try:
                killer = queue.get(block=False)
            except Empty:
                continue
            try:
                killer.kill()
            except OSError:
                pass

            i = 0
            while killer.is_alive() and i < 500:
                time.sleep(0.010)
                i += 1
            try:
                killer.force_kill()
            except OSError:
                pass

    def update_constants(self, v_internals : dict, build : Build, full_test_folder : str, out_path : str = None, node = None):

        bp = ('../' + npf.get_build_path()) if not os.path.isabs(npf.get_build_path()) else npf.get_build_path()
        rp = ('../' + build.build_path()) if not os.path.isabs(build.build_path()) else build.build_path()
        abs_test_folder = full_test_folder if os.path.isabs(full_test_folder) else npf.cwd_path() + os.sep + full_test_folder

        tp = os.path.relpath(self.path,abs_test_folder)

        if node and node.executor.path:
            bp = os.path.relpath(bp, npf.experiment_path() + '/testfolder/')
            rp = os.path.relpath(rp, npf.experiment_path() + '/testfolder/')
        v_internals.update({
                        'NPF_REPO':get_valid_filename(build.repo.name),
                        'NPF_REPO_PATH': rp,
                        'NPF_ROOT': '../', #Deprecated
                        'NPF_ROOT_PATH': os.path.relpath(npf.npf_root_path(), abs_test_folder),
                        'NPF_BUILD_PATH': bp,
                        'NPF_BUILD_ROOT': bp, #Deprecated
                        'NPF_SCRIPT_PATH': tp,
                        'NPF_TEST_PATH': tp, #Deprecatefd
                        'NPF_TESTIE_PATH': tp, #Deprecatefd
                        'NPF_RESULT_PATH': os.path.relpath(build.result_folder(), abs_test_folder)})
        if out_path:
            v_internals.update({'NPF_OUTPUT_PATH': os.path.relpath(out_path, abs_test_folder)})

    def parse_results(self, regex_list: str, output: str, new_kind_results: dict, new_data_results: dict) -> Tuple[
        bool, bool]:
        has_err = False
        has_values = False
        try:
            for result_regex in regex_list:
                for nr in re.finditer(result_regex, output.strip(), re.IGNORECASE):
                    result_type = nr.group("type")

                    kind = nr.group("kind")
                    if kind is None:
                        kind = "time"
                    kind_value = nr.group("kind_value")
                    if result_type is None:
                        result_type = ''
                    n = float(nr.group("value"))
                    mult = nr.group("multiplier")
                    unit = ""
                    if nr.group("unit"):
                        unit = nr.group("unit")
                    if unit.lower() == "sec" or unit.lower() == "s":
                        unit = "s"

                    if unit == "s":
                        if mult == "m":
                            n = n / 1000  # Keep all results in seconds
                        elif mult == "u" or mult == "µ":
                            n = n / 1000000
                        elif mult == "n":
                            n = n / 1000000000
                    else:
                        mult = mult.upper()

                    if mult == "K":
                        n *= 1024
                    elif mult == "M":
                        n *= 1024 * 1024
                    elif mult == "G":
                        n *= 1024 * 1024 * 1024
                    if n != 0 or (self.config.match("accept_zero", result_type)) or kind_value is not None:
                        result_add = self.config.get_bool_or_in("result_add", result_type)
                        result_append = self.config.get_bool_or_in("result_append", result_type)
                        if kind_value:
                            t = float(kind_value)
                            if result_type in new_kind_results.setdefault(kind,{}).setdefault(t, {}):
                                if result_add:
                                    new_kind_results[kind][t][result_type] += n
                                else:
                                    if type(new_kind_results[kind][t][result_type]) is not list:
                                        new_kind_results[kind][t][result_type] = [new_kind_results[kind][t][result_type]]

                                    new_kind_results[kind][t][result_type].append(n)
                            else:
                                new_kind_results[kind][t][result_type] = n
                        else:
                            if result_append:
                                new_data_results.setdefault(result_type,[]).append(n)
                            elif result_type in new_data_results and result_add:
                                new_data_results[result_type] += n
                            else:
                                new_data_results[result_type] = n
                        has_values = True
                    else:
                        print("Result for %s is 0 !" % result_type)
                        has_err = True

        except Exception as e:
            print("Exception while parsing results :")
            has_err = True
            raise e
        return has_err, has_values

    def execute(self, build, run, v, n_runs=1, n_retry=0, allowed_types=SectionScript.ALL_TYPES_SET, do_imports=True,
                test_folder=None, event=None, v_internals={}, before_test = None) \
            -> Tuple[Dict, Dict, str, str, int]:

        # Get address definition for roles from scripts
        self.parse_script_roles()

        # Create temporary folder
        deps_repo = []
        depscripts = [imp.test.scripts for imp in self.imports]

        allscripts = [item for sublist in [self.scripts] + depscripts for item in sublist]
        for script in allscripts:
            deps_repo.extend(script.get_deps_repos(self.options))
        for repo in deps_repo:
            if repo.version is not None:
                v_internals[repo.reponame.upper() + '_VERSION'] = repo.version
        v.update(v_internals)

        if test_folder is None:
            test_folder = self.make_test_folder()
            f_mine = True
        else:
            f_mine = False

        if not os.path.exists(npf.experiment_path() + '/' + test_folder):
            os.mkdir(npf.experiment_path() + '/' + test_folder)
        save_path = os.getcwd()
        os.chdir(npf.experiment_path() + '/' + test_folder)

        # Build file list
        file_list = []
        if SectionScript.TYPE_INIT in allowed_types:
            initv = {}
            for k, vinit in self.variables.statics().items():
                initv[k] = vinit.makeValues()[0]
            file_list.extend(self.build_file_list(initv, self.role, files=self.init_files))
        else:
            file_list.extend(self.build_file_list(v, self.role))

        n_exec = 0
        n_err = 0

        for imp in self.get_imports():
            imp.test.parse_script_roles()
            imp.imp_v = {}
            for k, val in imp.test.variables.statics().items():
                imp.imp_v[k] = val.makeValues()[0]

            imp.imp_v.update(v)

            for late_variables in imp.test.get_late_variables():
                imp.imp_v.update(late_variables.execute(imp.imp_v, imp.test))

            if SectionScript.TYPE_INIT in allowed_types:
                file_list.extend(imp.test.build_file_list(imp.imp_v, imp.get_role(), files=imp.test.init_files))
            else:
                file_list.extend(imp.test.build_file_list(imp.imp_v, imp.get_role()))

        self.create_files(file_list, test_folder)

        # Launching the tests in itself
        data_results = OrderedDict()  # dict of result_name -> [val, val, val]
        all_kind_results = {}  # dict of kind -> kind_value -> {result_name -> [val, val, val]}
        m = multiprocessing.Manager()
        all_output = []
        all_err = []
        for i in range(n_runs):
            for i_try in range(n_retry + 1):
                if i_try > 0 and not self.options.quiet:
                    print("Re-try tests %d/%d..." % (i_try, n_retry + 1))
                output = ''
                err = ''

                if before_test:
                    before_test(i,i_try)

                queue = m.Queue()

                event = EventBus(m)

                remote_params = []
                for t, v, role in (
                                          [(imp.test, imp.imp_v, imp.get_role()) for imp in
                                           self.imports] if do_imports else []) + [
                                      (self, v, None)]:
                  for script in t.scripts:
                    srole = role if role else script.get_role()
                    nodes = npf.nodes_for_role(srole)

                    autokill = m.Value('i', 0) if npf.parseBool(script.params.get("autokill", t.config["autokill"])) else None
                    v["NPF_NODE_MAX"] = len(nodes)
                    for i_node, node in enumerate(nodes):
                      v["NPF_NODE"] = node.get_name()
                      v["NPF_NODE_ID"] = i_node
                      multi = script.multi

                      if multi is None:
                          multi = [0]
                      elif multi == '*':
                          if node.multi:
                              multi = range(1, node.multi + 1)
                          else:
                              multi = [1]
                      elif type(multi) == str:
                          multi = [int(multi)]

                      for i_multi in multi:
                        if autokill is not None:
                            autokill.value = autokill.value + 1
                        if not script.get_type() in (allowed_types.difference(set([SectionScript.TYPE_EXIT]))):
                            continue
                        param = RemoteParameters()
                        param.sudo = script.params.get("sudo", False)

                        remote_test_folder = node.experiment_path() + os.sep + test_folder + os.sep
                        self.update_constants(v, build, remote_test_folder, out_path=None, node=node)
                        v["NPF_MULTI"] = i_multi
                        v["NPF_MULTI_ID"] = i_multi
                        v["NPF_MULTI_MAX"] = node.multi if node.multi is not None else 1
                        v["NPF_ARRAY_ID"] = (i_node * v["NPF_MULTI_MAX"]) + i_multi
                        v["NPF_ARRAY_MAX"] = len(nodes) * v["NPF_MULTI_MAX"]

                        #Checking if the script has a filter
                        c = True # Should we continue?
                        for ik, iv in script.params.items():
                            if ik.startswith('ifeq-'):
                                ik=ik[5:]
                                if ik not in v:
                                    print("WARNING: Filtering for %s for script %s but it is not in the variables" % (ik, param.title))
                                if v[ik] != iv:
                                    c = False
                                    break

                        if not c:
                            continue

                        if node.mode == "netns" and i_multi > 0:
                            param.virt = "ip netns exec npfns%d" % i_multi
                            param.sudo = True

                        param.commands = "mkdir -p " + test_folder + " && cd " + test_folder + ";\n" + SectionVariable.replace_variables(
                            v,
                            script.content,
                            self_role = srole, self_node=node,
                            default_role_map= self.config.get_dict(
                                "default_role_map"))
                        param.options = self.options
                        param.queue = queue
                        param.stdin = t.stdin.content
                        timeout = t.config['timeout']
                        if 'timeout' in script.params:
                            timeout = float(script.params['timeout'])
                        if self.config['timeout'] == -1 or self.config['timeout'] > timeout:
                            timeout = self.config['timeout']
                        if timeout == -1 or timeout == "-1":
                            timeout = None

                        param.timeout = timeout
                        script.timeout = timeout
                        param.role = srole
                        param.role_id = i_node
                        param.default_role_map = self.config.get_dict("default_role_map")
                        param.delay = script.delay()

                        deps_bin_path = [repo.get_remote_bin_folder(node) for repo in script.get_deps_repos(self.options) if
                                         not repo.reponame in self.options.ignore_deps]
                        param.bin_paths = deps_bin_path + [build.get_remote_bin_folder(node)]
                        param.testdir = test_folder
                        param.event = event
                        param.script = script
                        param.name = script.get_name(True)
                        param.autokill = autokill
                        param.env = OrderedDict()
                        param.env.update(v_internals)
                        param.env.update([(k, v.replace('$NPF_BUILD_PATH', build.repo.get_build_path())) for k, v in
                                          build.repo.env.items()])

                        if self.options.rand_env:
                            param.env['RANDENV'] = ''.join(random.choice(string.ascii_lowercase) for i in range(random.randint(0,self.options.rand_env)))
                        if 'waitfor' in script.params:
                            param.waitfor = script.params['waitfor']

                        remote_params.append(param)

                n = len(remote_params)
                n_exec += n
                if n == 0:
                    break
                try:
                    if self.options.allow_mp:
                        p = multiprocessing.Pool(n)
                        parallel_execs = p.map(_parallel_exec,
                                               remote_params)
                    else:
                        print("Sequential execution...")
                        parallel_execs = []
                        for remoteParam in remote_params:
                            parallel_execs.append(_parallel_exec(remoteParam))

                except KeyboardInterrupt:
                    print("Program is interrupted")
                    if self.options.allow_mp:
                        p.close()
                        p.terminate()

                    if not self.options.preserve_temp:
                        for imp in self.imports:
                            imp.test.cleanup()
                        self.cleanup()
                    os.chdir('..')
                    if not self.options.preserve_temp:
                        shutil.rmtree(test_folder)
                    else:
                        print("Test files have been preserved in :" + test_folder)
                    sys.exit(1)

                if self.options.allow_mp:
                    p.close()
                    p.terminate()
                worked = False
                critical_failed = False

                for iscript, (r, o, e, c, script) in enumerate(parallel_execs):
                    if r == 0:
                        print("Timeout of %d seconds expired for script %s on %s..." % (
                            script.timeout, script.get_name(), script.get_role()))
                        if self.options.quiet:
                            print("stdout:")
                            print(o)
                            print("stderr:")
                            print(e)
                        continue
                    if r == -1:
                        os.chdir('..')
                        if not self.options.preserve_temp and f_mine:
                            shutil.rmtree(test_folder)
                        sys.exit(1)
                    if c != 0:
                        n_err = n_err + 1
                        if npf.parseBool(script.params.get("critical", t.config["critical"])):
                            critical_failed = True
                            print("[ERROR] A critical script failed ! Results will be ignored")
                        print("Bad return code (%d) for script %s on %s ! Something probably went wrong..." % (
                            c, script.get_name(), script.get_role()))
                        if self.options.quiet:
                            print("stdout:")
                            print(o)
                            print("stderr:")
                            print(e)
                        continue

                for iparallel, (r, o, e, c, script) in enumerate(parallel_execs):
                    if len(self.scripts) > 1:
                        output += "stdout of script %s on %s :\n" % (script.get_name(), script.get_role())
                        err += "stderr of script %s on %s :\n" % (script.get_name(), script.get_role())

                    if r:
                        worked = True
                        output += o
                        err += e

                if SectionScript.TYPE_EXIT in allowed_types:
                 for s,vlist in [(t.test,t.imp_v) for t in self.imports] + [(self, v)]:
                  for script in s.get_scripts():
                    if not script.type == SectionScript.TYPE_EXIT:
                        continue
                    exitscripts=script.content
                    role_map = self.config.get_dict("default_role_map")
                    role = None

                    role = script.get_role()

                    for i_node, node in enumerate(npf.nodes_for_role(role, role_map)):
                        vlist["NPF_NODE"] = node.get_name()
                        vlist["NPF_NODE_ID"] = i_node

                        cmd = SectionVariable.replace_variables(
                            vlist,
                            exitscripts,self_role = role, default_role_map = role_map)
                        executor=node.executor
                        ncmd = "mkdir -p " + test_folder + " && cd " + test_folder + ";\n" + cmd
                        try:
                            pid, s_output, s_err, c = executor.exec(cmd=ncmd, options=self.options)
                        except Exception as e:
                            print("An error occured!", e)
                        #print(s_output, s_err)
                        output += s_output
                        err += s_err


                all_output.append(output)
                all_err.append(err)

                if not worked or critical_failed:
                    continue

                if not self.config["result_regex"]:
                    break

                has_values = False
                has_err = False
                new_data_results = {}
                new_kind_results = {}
                new_kind_results.setdefault("time", {})
                regex_list = self.config.get_list("result_regex")

                this_has_err, this_has_value = self.parse_results(regex_list, output, new_kind_results,
                                                                  new_data_results)

                if this_has_err:
                    has_err = True
                if this_has_value:
                    has_values = True
                if hasattr(self, 'pyexit') and allowed_types != set([SectionScript.TYPE_INIT]):
                    vs = {'RESULTS': new_data_results, 'TIME_RESULTS': new_kind_results["time"], 'KIND_RESULTS':new_kind_results}
                    vs.update(v)
                    try:
                        exec(self.pyexit.content, vs)
                    except SystemExit as e:
                        if e.code != 0:
                            print("ERROR WHILE EXECUTING PYEXIT SCRIPT: returned code %d" % e.code)
                        pass
                    except Exception as e:
                        print("ERROR WHILE EXECUTING PYEXIT SCRIPT:")
                        print(e)


                glob_sync = self.config.get_list("glob_sync")
                glob_min = []
                for g in glob_sync:
                    for kind, kind_results in new_kind_results.items():
                        if kind in glob_sync:
                            mg = min(kind_results.keys())
                            glob_min.append(mg)

                for kind, kind_results in new_kind_results.items():
                  if kind_results:
                    all_kind_results.setdefault(kind,{})
                    if kind in glob_sync:
                        min_kind_value = min(glob_min)
                    else:
                        min_kind_value = min(kind_results.keys())
                    nonzero = set()
                    update = {}
                    all_result_types = set()
                    nz = False
                    accept_zero = not self.config.match("accept_zero", kind)
                    if accept_zero:
                        nz = False

                    last_val = {}
                    acc = self.config.get_list("time_sync")
                    for kind_value, results in sorted(kind_results.items()):
                        if not nz: #We still haven't found a non zero kind_value
                            for result_type, result in results.items():
                                if result_type in self.config.get_list("var_repeat"):
                                    last_val[result_type] = result

                                if result != 0:
                                    nz = True
                                    if (not acc or result_type in acc) and not kind in glob_sync:
                                        min_kind_value = kind_value
                            if not nz:
                                continue
                            else:
                                for result_type, result in last_val.items():
                                    results[result_type] = result

                        for result_type, result in results.items():
                            if result_type in self.config.get_dict("var_n_runs") and i >= int(
                                    self.config.get_dict("var_n_runs")[result_type]):
                                continue
                            nonzero.add(result_type)
                            all_result_types.add(result_type)
                            event_t = Decimal(
                                ("%.0" + str(self.config['time_precision']) + "f") % round(float(kind_value - (min_kind_value if self.config.get_bool_or_in("time_sync", kind) else 0)), int(
                                    self.config['time_precision'])))
                            update.setdefault(event_t, {}).setdefault(result_type, [])
                            update[event_t][result_type].extend(result if type(result) is list else [result])
                            if result_type in self.config.get_list("var_repeat"):
                                # Replicate existing time series for all new incoming time points
                                self.ensure_time(event_t, result_type, all_kind_results[kind])

                    # Replicate new results for every time point
                    for event_t, results in update.items():
                        for result_type, result in results.items():
                            if result_type in self.config.get_list("var_repeat"):
                                self.ensure_time(event_t, result_type, update)

                    for kind_value, results in update.items():
                        for result_type, result in results.items():
                            all_kind_results[kind].setdefault(kind_value, {}).setdefault(result_type, []).extend(result)

                    last_v=0
                    for kind_value, results in update.items():
                        for result_type, result in results.items():
                            if not result:
                                continue
                            last_v = np.mean(result)

                    diff = all_result_types.difference(nonzero)
                    if diff:
                        print("Result for %s is 0 !" % ', '.join(diff))
                        has_err = True
                for result_type, result in new_data_results.items():
                    data_results.setdefault(result_type, []).extend(result if type(result) == list else [result])
                if has_values:
                    break

                if script.type == SectionScript.TYPE_SCRIPT:
                  for result_type in self.config.get_list('results_expect'):
                    if result_type not in data_results and not result_type in all_kind_results:
                        print("Could not find expected result '%s' !" % result_type)
                        has_err = True

                  if len(data_results) + sum([len(r) for k, r in all_kind_results.items()]) == 0:
                    print("Could not find any results ! Something probably went wrong, check the output :")

                    has_err = True

                if has_err and self.options.quiet:
                    print("stdout:")
                    print(output)
                    print("stderr:")
                    print(err)

        if not self.options.preserve_temp:
            for imp in self.imports:
                imp.test.cleanup()
            self.cleanup()
        os.chdir(save_path)
        if not self.options.preserve_temp and f_mine:
            try:
                shutil.rmtree(test_folder)
            except FileNotFoundError:
                print("Could not delete folder %s..." % test_folder)
        return data_results, all_kind_results, all_output, all_err, n_exec, n_err

    def ensure_time(self, event_t, result_type, update):
        if event_t in update:
            if result_type in update[event_t]:
                return
        else:
            update[event_t] = {}

        # Find the previous point
        prev = None
        mindist = Decimal('Inf')
        for u_t, u_r in update.items():
            if u_t > event_t:
                continue
            if result_type not in u_r:
                continue
            dist = float(event_t) - float(u_t)
            if dist < mindist:
                prev = u_t
                mindist = dist
        if prev is not None:
            update[event_t][result_type] = update[prev][result_type].copy()
        else:
            update[event_t][result_type] = []

    def do_init_all(self, build, options, do_test, allowed_types=SectionScript.ALL_TYPES_SET, test_folder=None,
                    v_internals={}):
        if not build.build(options.force_build, options.no_build, options.quiet_build, options.show_build_cmd):
            raise ScriptInitException()
        if not self.build_deps([build.repo], v_internals=v_internals, no_build=options.no_build):
            raise ScriptInitException()

        if (allowed_types is None or "init" in allowed_types) and options.do_init:
            if not options.quiet:
                print("Executing init scripts...")
            vs = {}
            for k, v in self.variables.statics().items():
                vs[k] = v.makeValues()[0]
            for late_variables in self.get_late_variables():
                vs.update(late_variables.execute(vs, self, fail=False))
            data_results, all_kind_results, output, err, num_exec, num_err = self.execute(build, Run(vs), v=vs, n_runs=1,
                                                                                      n_retry=0,
                                                                                      allowed_types={"init"},
                                                                                      do_imports=True,
                                                                                      test_folder=test_folder,
                                                                                      v_internals=v_internals)

            if num_err > 0:
                if not options.quiet:
                    print("Aborting as init scripts did not run correctly !")
                    print("Stdout:")
                    print("\n".join(output))
                    print("Stderr:")
                    print("\n".join(err))
                raise ScriptInitException()

    def execute_all(self, build, options, prev_results: Dataset = None, do_test=True, on_finish=None,
                    allowed_types=SectionScript.ALL_TYPES_SET, prev_kind_results: Dict[str, Dataset] = None, iserie=0,nseries=1) -> Tuple[
        Dataset, bool]:
        """Execute script for all variables combinations. All tools reliy on this function for execution of the test
        :param allowed_types:Tyeps of scripts allowed to run. Set with either init, scripts or both
        :param do_test: Actually run the tests
        :param options: NPF options object
        :param build: A build object
        :param prev_results: Previous set of result for the same build to update or retrieve
        :return: Dataset(Dict of variables as key and arrays of results as value)
        """
        if not prev_kind_results:
            prev_kind_results = {}

        init_done = False
        test_folder = self.make_test_folder()

        #All the following paths must be relative to the NPF experiment root folder (that is something like NPF's folder/test1234567/)
        full_test_folder = npf.from_experiment_path(test_folder) + os.sep

        dirname, basename, ext = npf.splitpath(options.output if options.output != 'graph' else options.graph_filename)
        out_path = dirname + os.sep
        v_internals = {}
        self.update_constants(v_internals, build, full_test_folder, out_path)

        if not SectionScript.TYPE_SCRIPT in allowed_types:
            # If scripts is not in allowed_types, we have to run the init by force now

            self.do_init_all(build, options, do_test=do_test, allowed_types=allowed_types, v_internals=v_internals)
            if not self.options.preserve_temp:
                shutil.rmtree(test_folder)
            return {}, True

        all_data_results = OrderedDict()
        all_kind_results = OrderedDict()
        # If one first, we first ensure 1 result per variables then n_runs
        if options.onefirst:
            total_runs = [1, self.config["n_runs"]]
        else:
            total_runs = [self.config["n_runs"]]

        for runs_this_pass in total_runs:  # Number of results to ensure for this run
            n = 0
            overriden = set(build.repo.overriden_variables.keys())
            all_variables = list(self.variables.expand(method=options.expand, overriden=overriden))
            n_tests = len(all_variables)
            for root_variables in all_variables:
                n += 1

                variables = {}
                shadow_variables = {}
                for imp in self.get_imports():
                  #If the module is an include, the variables should be visible to the user, for a real module, it's only a default initialization
                  if imp.is_include:
                    for k,v in imp.test.variables.statics().items():
                        variables[k] = v.makeValues()[0]

                run = Run(variables)
                variables.update(root_variables)
                run.variables.update(build.repo.overriden_variables)
                variables = run.variables.copy()

                if shadow_variables:
                    shadow_variables.update(root_variables)
                    shadow_variables.update(build.repo.overriden_variables)
                    variables.update(shadow_variables)

                for late_variables in self.get_late_variables():
                    variables.update(late_variables.execute({**variables, **v_internals}, test=self))

                for imp in self.get_imports():
                  if imp.is_include:
                    for late_variables in imp.test.get_late_variables():
                        variables.update(late_variables.execute({**variables, **v_internals}, imp.test))

                r_status, r_out, r_err = self.test_require(variables, build)
                if not r_status:
                    if not self.options.quiet:
                        print("Requirement not met for %s" % run.format_variables(self.config["var_hide"]))
                        if r_out.strip():
                            print(r_out.strip())
                        if r_err.strip():
                            print(r_err.strip())

                    continue

                if prev_results and prev_results is not None and not (options.force_test or options.force_retest):
                    run_results = prev_results.get(run, None)
                    if run_results is None:
                        run_results = {}
                else:
                    run_results = {}

                kind_results = {} #kind->(run_with_time -> results))
                kind_results["time"] = OrderedDict()
                config_time_kinds = self.config.get_list("time_kinds")
                if prev_kind_results and not (options.force_test or options.force_retest):
                    nprev_kind_results = {}
                    for kind, prev_kresults in prev_kind_results.items():
                        if config_time_kinds and not kind in config_time_kinds:
                            continue
                        nprev_kresults = OrderedDict()
                        kind_results.setdefault(kind,OrderedDict())
                        for trun, results in prev_kresults.items():
                            if run.inside(trun):
                                kind_results[kind][trun] = results
                            else:
                                nprev_kresults[trun] = results
                        nprev_kind_results[kind] = nprev_kresults
                    prev_kind_results = nprev_kind_results
                if not run_results and options.use_last and build.repo.url:
                    for version in build.repo.method.get_history(build.version, limit=options.use_last):
                        oldb = Build(build.repo, version)
                        r = oldb.load_results(self)
                        if r and run in r:
                            run_results = r[run]
                            break
                if not kind_results and options.use_last and build.repo.url:
                    for version in build.repo.method.get_history(build.version, limit=options.use_last):
                        oldb = Build(build.repo, version)
                        r = oldb.load_results(self, kind=True)
                        found = False
                        if r:
                            for kind, kr in r.items():
                              kind_results.setdefault(kind, OrderedDict)
                              for r_run, results in kr.items():
                                if run in results:
                                    kind_results[kind][r_run] = results[run]
                                    found = True
                        if found:
                            break

                if run_results:
                    for result_type in self.config.get_list('results_expect'):
                        print("Could not find result :", self.config.get_list('results_expect'))
                        if result_type not in run_results:
                            found = False
                            if prev_kind_results:
                              for kind, kr in prev_kind_results.items():
                                for run_kind, results in kr.items():
                                    if result_type in results:
                                        found = True
                                        continue
                            if not found:
                                print("Missing result type %s, re-doing the run" % result_type)
                                run_results = {}
                                prev_kind_results = {}


                have_new_results = False

                #Compute the minimal number of existing results, so we know how much runs we must do
                l=[]
                dall=True
                n_existing_results=[]
                for result_type, results in run_results.items():
                    if self.config.match("accept_zero", result_type):
                        continue
                    if not results:
                        continue
                    n_existing_results.append(len(results))
                    if len(results) < runs_this_pass:
                        l.append(result_type)
                    else:
                        dall=False

                if len(n_existing_results) == 0:
                    n_existing_results = 0
                else:
                    if options.min_test:
                        n_existing_results = min(n_existing_results)
                    else:
                        n_existing_results = max(n_existing_results)

                n_runs = runs_this_pass - (
                    0 if (options.force_test or options.force_retest) or len(run_results) == 0 else n_existing_results)
                if n_runs > 0 and do_test:
                    if not init_done:
                        self.do_init_all(build, options, do_test, allowed_types=allowed_types, test_folder=test_folder,
                                         v_internals=v_internals)
                        init_done = True

                    def print_header(i, i_try):
                        pass
                    if not self.options.quiet:
                        if len(run_results) > 0:
                            if not dall:
                                print("Results %s are missing some points..." % ", ".join(l))
                        if n_tests > 0:
                            def print_header(i, i_try):
                                n_try=int(self.config["n_retry"])
                                desc = run.format_variables(self.config["var_hide"])
                                if desc:
                                    print(desc, end=' ')
                                print(
                                  ("[%srun %d/%d for test %d/%d"+(" of serie %d/%d" %(iserie+1,nseries) if nseries > 1 else "")+"]") % (  ("retrying %d/%d " % (i_try + 1,n_try)) if i_try > 0 else "", i+1, n_runs, n, n_tests))

                    new_data_results, new_all_kind_results, output, err, n_exec, n_err = self.execute(build, run, variables,
                                                                                                  n_runs,
                                                                                                  n_retry=self.config[
                                                                                                      "n_retry"],
                                                                                                  allowed_types={
                                                                                                      SectionScript.TYPE_SCRIPT, SectionScript.TYPE_EXIT},
                                                                                                  test_folder=test_folder,
                                                                                                  v_internals=v_internals, before_test = print_header)
                    if new_data_results:
                        for result_type, values in new_data_results.items():
                            if values is None:
                                continue
                            if options.force_retest:
                                run_results[result_type] = values
                            else:
                                if result_type in run_results and run_results[result_type] is not None:
                                    run_results[result_type].extend(values)
                                else:
                                    run_results[result_type] = values

                            have_new_results = True
                    if new_all_kind_results:
                        have_new_results = True
                else:
                    if not self.options.quiet:
                        print(run.format_variables(self.config["var_hide"]))

                if len(run_results) > 0:
                    if not self.options.quiet:
                        if len(run_results) == 1:
                            print(list(run_results.values())[0])
                        else:
                            print(", ".join(['{0}: {1}'.format(k, run_results[k]) for k in sorted(run_results)]))

                    all_data_results[run] = run_results
                else:
                    all_data_results[run] = {}

                if have_new_results and sum([len(r) for kind,r in new_all_kind_results.items()]) > 0:
                    for kind, kresults in new_all_kind_results.items():
                      kind_results.setdefault(kind, OrderedDict())
                      for time, results in sorted(kresults.items()):
                        time_run = Run(run.variables.copy())
                        time_run.variables[kind] = time
                        for result_type, result in results.items():
                            rt = kind_results[kind].setdefault(time_run, {}).setdefault(result_type, [])
                            if options.force_retest:
                                rt.clear()
                            rt.extend(result)
                for kind, kresults in kind_results.items():
                  all_kind_results.setdefault(kind, OrderedDict())
                  for result_type, result in kresults.items():
                    all_kind_results[kind][result_type] = result

                if self.options.print_time_results:
                    for kind, kresults in all_kind_results.items():
                        print("%s:" % kind)
                        print(kresults)

                if on_finish and have_new_results:
                    def call_finish():
                        on_finish(all_data_results, all_kind_results)

                    thread = threading.Thread(target=call_finish, args=())
                    thread.daemon = True
                    thread.start()

                # Save results
                if all_data_results and have_new_results:
                    if prev_results or prev_kind_results:
                        if all_data_results[run]:
                            if prev_results is None:
                                prev_results = {}
                            prev_results[run] = all_data_results[run]
                        build.writeversion(self, prev_results, allow_overwrite=True)
                        for kind, kr in kind_results.items():
                            prev_kind_results.setdefault(kind,OrderedDict())
                            prev_kind_results[kind].update(kind_results[kind])
                        build.writeversion(self, prev_kind_results, allow_overwrite=True, kind=True, reload=False)
                    else:
                        build.writeversion(self, all_data_results, allow_overwrite=True)
                        build.writeversion(self, all_kind_results, allow_overwrite=True, kind=True)

        if not self.options.preserve_temp:
            try:
                shutil.rmtree(npf.experiment_path() + os.sep + test_folder)
            except PermissionError:
                pass
        else:
            print("Test files have been kept in folder %s" % test_folder)

        return all_data_results, all_kind_results, init_done

    def get_title(self):
        if "title" in self.config and self.config["title"] is not None:
            title = self.config["title"]
        elif hasattr(self, "info"):
            title = self.info.content.strip().split('\n', 1)[0]
        else:
            title = self.filename
        return title

    def reject_outliers(self, data):
        m = self.config["accept_outliers_mult"]
        mean = np.mean(data)
        std = np.std(data)
        data = data[abs(data - mean) <= m * std]
        return data

    @staticmethod
    def expand_folder(test_path, options, tags=None) -> List['Test']:
        tests = []
        if not os.path.exists(test_path):
            print("The npf script path %s does not exist" % test_path)
            return tests
        if os.path.isfile(test_path):
            test = Test(test_path, options=options, tags=tags)
            tests.append(test)
        else:
            for root, dirs, files in os.walk(test_path):
                for filename in files:
                    if filename.endswith(".test") or filename.endswith(".npf"):
                        try:
                            test = Test(os.path.join(root, filename), options=options, tags=tags)
                            tests.append(test)
                        except Exception as e:
                            print("Error during the parsing of %s :\n%s" % (filename, e))

        filtered_tests = []
        for test in tests:
            missing_tags = test.test_tags()
            if len(missing_tags) > 0:
                if not options.quiet:
                    print(
                        "Passing test %s as it lacks tags %s" % (test.filename, ','.join(missing_tags)))
            else:
                if test.test_roles_mapping():
                    filtered_tests.append(test)
                else:
                    raise Exception(
                        "Roles %s cannot be on the same node ! Please use --cluster argument to set them accross nodes" % ' and '.join(
                           test.config.get_list("role_exclude")))

        return filtered_tests

    def test_roles_mapping(self):
        for excludes in self.config.get_list("role_exclude"):
            s = excludes.split('+')
            m = set()
            for role in s:
                nodes = npf.nodes_for_role(role)
                for node in nodes:
                  if node in m:
                    return False
                  m.add(node)
        return True

    def parse_script_roles(self):
        """
        Look for parameters of scripts and imports for configuration that affects the test, such as NICs parameters like
        the IP address
        """
        for script in (self.scripts + self.imports):
            for k, val in script.params.items():
                nic_match = re.match(r'(?P<nic_idx>[0-9]+)[:](?P<type>' + NIC.TYPES + '+)', k, re.IGNORECASE)
                if nic_match:
                    npf.nodes_for_role(script.get_role(), self.config.get_dict("default_role_map"))[0].get_nic(
                        int(nic_match.group('nic_idx')))[nic_match.group('type')] = val

    def get_imports(self) -> List[SectionImport]:
        return self.imports

    def get_late_variables(self) -> List[SectionLateVariable]:
        return self.late_variables

    def make_test_folder(self):
        test_folder = "test%s-%05d" % (datetime.datetime.now().strftime("%y%m%d%H%M"), random.randint(1, 2 << 16))
        os.mkdir(npf.experiment_path() + os.sep + test_folder)
        return test_folder
