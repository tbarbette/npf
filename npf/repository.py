import os
import tarfile
import urllib
from collections import OrderedDict
from abc import ABCMeta
from pathlib import Path
import re
from urllib.error import URLError
import urllib.request

import shutil

import gitdb

from npf import npf
from npf.build import Build
from .variable import is_numeric, VariableFactory

import git

repo_variables = ['name', 'branch', 'configure', 'url', 'method', 'parent', 'tags', 'make', 'version', 'clean', 'build_info',
                  'bin_folder', 'bin_name', 'env']


class Method(metaclass=ABCMeta):
    def __init__(self, repo):
        self.repo = repo


class MethodGit(Method):
    __gitrepo = None
    _fetch_done = False

    def gitrepo(self) -> git.Repo:
        if (self.__gitrepo):
            return self.__gitrepo
        else:
            return self.checkout()

    def get_last_versions(self, limit=100, branch=None, force_fetch=False):
        origin = self.gitrepo().remote('origin')
        if not self.repo.options.no_build and (force_fetch or not self._fetch_done):
            if not self.repo.options.quiet_build:
                print("Fetching last versions of %s..." % self.repo.reponame)
            origin.fetch()
            self._fetch_done = True

        if branch is None:
            branch = self.repo.branch

        try:
            b_commit = self.gitrepo().commit('origin/' + branch)
        except gitdb.exc.BadName:
            b_commit = self.gitrepo().tag('refs/tags/' + branch).commit

#        for i, commit in enumerate(b_commit.iter_items(repo=b_commit.repo, rev=b_commit, skip=0)):
        # The above is not suitable as we don't care about the "fake" merged commits
        versions = self.get_history(version=b_commit, limit = limit - 1)
        return [b_commit.hexsha[:7]] + versions

    def get_history(self, version, limit=1):
        versions = []
        i_commit = next(self.gitrepo().iter_commits(version)).parents[0]
        while len(versions) < limit:
            versions.append(i_commit.hexsha[:7])
            if len(i_commit.parents) == 0:
                break
            i_commit = i_commit.parents[0]

        return versions


    def is_checkout_needed(self, version):
        gitrepo = self.gitrepo()
        if gitrepo.head.commit.hexsha[:7] != version:
            return True
        return False

    def checkout(self, branch=None) -> git.Repo:
        """
        Checkout the repo to its folder, fetch if it already exists
        :param branch: An optional branch
        :return:
        """
        if not branch:
            branch = self.repo.branch

        need_clone=False
        if os.path.exists(self.repo.get_build_path()):
            try:
                gitrepo = git.Repo(self.repo.get_build_path())
                o = gitrepo.remotes.origin
                if not self.repo.options.no_build and not self._fetch_done:
                    o.fetch()
                    self._fetch_done = True
            except git.exc.InvalidGitRepositoryError:
                print("Path %s appear to be invalid" % self.repo.get_build_path())
                #shutil.rmtree(self.repo.get_build_path())
                need_clone=True
        else:
            need_clone=True

        if need_clone:
            if not self.repo.options.quiet_build:
                print("Cloning %s from %s..." % (self.repo.reponame, self.repo.url))
            gitrepo = git.Repo.clone_from(self.repo.url, self.repo.get_build_path())

        if branch in gitrepo.remotes.origin.refs:
            c = gitrepo.remotes.origin.refs[branch]
        else:
            c = branch

        if gitrepo.head.commit != gitrepo.commit(c) and not self.repo.options.no_build:
            if not self.repo.options.quiet_build:
                print("Reseting branch to latest %s" % (c))
            gitrepo.git.stash('save')
            gitrepo.head.reset(commit=c, index=True, working_tree=True)

        self.__gitrepo = gitrepo
        return gitrepo


class UnversionedMethod(Method, metaclass=ABCMeta):
    def __init__(self, repo):
        super().__init__(repo)
        if not repo.version:
            repo.version = "unknown"

    def get_last_versions(self, limit=None, branch=None, force_fetch=False):
        return [self.repo.version]

    def get_history(self, version, limit):
        return []


class MethodGet(UnversionedMethod):
    def checkout(self, branch=None):
        if branch is None:
            branch = self.repo.version
        url = npf.replace_path(self.repo.url,Build(self.repo,branch,self.repo.options.result_path))
        if not Path(self.repo.get_build_path()).exists():
            os.makedirs(self.repo.get_build_path())
        try:
            proxy = urllib.request.ProxyHandler({})
            opener = urllib.request.build_opener(proxy)
            opener.addheaders = [('User-Agent', 'NPF')]
            urllib.request.install_opener(opener)
            filename, headers = urllib.request.urlretrieve(url, self.repo.get_build_path() + os.path.basename(url))
        except URLError:
            print("ERROR : Could not download %s : bad URL?" % url)
            return False
        t = tarfile.open(filename)
        t.extractall(self.repo.get_build_path())
        t.close()
        os.unlink(filename)
        return True

class MethodLocal(UnversionedMethod):
    def checkout(self, branch=None):
        if branch is None:
            branch = self.repo.version
        if not Path(self.repo.get_build_path()).exists():
            print("WARNING: %s does not exist" % self.repo.get_build_path())
            return False
        return True


class MethodPackage(UnversionedMethod):
    def checkout(self, branch=None):
        if not Path(self.repo.get_build_path()).exists():
            os.makedirs(self.repo.get_build_path())
        return True


repo_methods = {'git': MethodGit, 'get': MethodGet, 'package': MethodPackage, 'local': MethodLocal}


class Repository:
    _repo_cache = {}


    method = repo_methods['git']

    def __init__(self, repo, options):
        self.name = None
        self._current_build = None

        version = repo.split('@')
        if len(version) > 1:
            self.version=version[1]
        else:
            self.version=None
        overwrite_name = version[0].split(':')
        add_tags = overwrite_name[0].split('+')
        overwrite_branch = add_tags[0].split('/',1)

        self.reponame = overwrite_branch[0]
        self.tags = []
        self.options = options
        self.branch = 'master'
        self.make = 'make -j12'
        self.clean = 'make clean'
        self.bin_folder = 'bin'
        self.env = OrderedDict()
        self.bin_name = self.reponame  # Wild guess that may work some times...
        self.build_info = None
        self.configure = ''
        self._last_100 = None

        if self.reponame == 'None':
            self.url = None
        else:
            repo_path = npf.find_local('repo/' + self.reponame + '.repo', critical=True)

            f = open(repo_path, 'r')
            for line in f:
                line = line.strip()
                line = re.sub(r'(^|[ ])//.*$', '', line)
                if line.startswith("#"):
                    continue
                if not line:
                    continue
                s = line.split('=', 1)
                var = s[0].strip()
                var = var.split(':',1)
                if len(var) > 1:
                    have_all=True
                    for v in var[0].split(','):
                        if not v in options.tags:
                            have_all = False
                            break
                    if not have_all:
                        continue
                    self.reponame += '-' + var[0]
                    var = var[1]
                else:
                    var = var[0]
                val = s[1].strip()
                append = False
                if var.endswith('+'):
                    var = var[:-1]
                    append = True

                if is_numeric(val) and var != 'branch':
                    val = float(val)
                    if val.is_integer():
                        val = int(val)
                if not var in repo_variables:
                    raise Exception("Unknown variable %s" % var)
                elif var == "parent":
                    parent = Repository(val, options)
                    for attr in repo_variables:
                        if not hasattr(parent, attr):
                            continue
                        pval = getattr(parent, attr)
                        if attr == "method":
                            for m, c in repo_methods.items():
                                if c == type(pval):
                                    method = m
                                    break
                        else:
                            setattr(self, attr, pval)
                elif var == "method":
                    val = val.lower()
                    if not val in repo_methods:
                        raise Exception("Unknown method %s" % val)
                    val = repo_methods[val]
                elif var == "tags":
                    if append:
                        self.tags += val.split(',')
                    else:
                        self.tags = val.split(',')
                    continue

                elif var == "env":
                    ed = VariableFactory.build(var, val).vdict
                    if append:
                        self.env += ed
                    else:
                        self.env = ed
                    continue

                if append:
                    setattr(self, var, getattr(self, var) + " " + val)
                else:
                    setattr(self, var, val)

            self.method = self.method(self)  # Instanciate the method

        self.overriden_variables = {}
        if len(add_tags) > 1:
            for spec in add_tags[1].split(','):
                sp = spec.split('=')
                if len(sp) == 1:
                    self.tags.append(spec)
                else:
                    self.overriden_variables[sp[0]] = sp[1]
            self._id = self.reponame + "-" + add_tags[1]
        else:
            self._id = self.reponame


        if len(overwrite_branch) > 1:
            self.branch = overwrite_branch[1]

        if len(overwrite_name) > 1:
            self.name = overwrite_name[1]

        if type(self.method) == MethodLocal:
            path = overwrite_branch[1] if len(overwrite_branch) > 1 else self.url
            if path:
                try:
                    self._build_path = path if os.path.isabs(path) else npf.find_local(path, critical=True, suppl = [os.path.dirname(repo_path)] if repo_path else [])
                except FileNotFoundError:
                    raise Exception("The URL of the local repository '%s' is invalid. Maybe try an absolute path?" % path)
            else:
                self._build_path = path
        else:
            self._build_path = npf.get_build_path() + self.reponame
        #Ensure trailing /
        self._build_path = os.path.join(self._build_path,'')

    def get_identifier(self):
        return self._id

    def get_reponame(self):
        return self.reponame

    def pretty_name(self):
        return self.name

    #Get the path
    def get_build_path(self):
        return self._build_path

    #Get the path to the binary folder of this build on a remote node
    def get_remote_build_path(self, node):
        bp = self.get_build_path()
        if node.nfs:
            return bp
        if not bp:
            return ""
        #If the path is in the NPF build path, the remote
        if os.path.abspath(bp).startswith(npf.get_build_path()):
            return os.path.relpath(bp, os.path.dirname(os.path.normpath(npf.get_build_path())))
        if os.path.abspath(bp).startswith(npf.experiment_path()):
            return os.path.relpath(bp, npf.experiment_path())
        if os.path.abspath(bp).startswith(npf.npf_root_path()):
            return os.path.relpath(bp, npf.npf_root_path())
        return os.path.basename(bp)


    def get_local_bin_folder(self, version=None):
        return self._get_bin_folder(version=version)

    def get_remote_bin_folder(self, remote, version=None):
        return self._get_bin_folder(version=version, remote=remote)

    def _get_bin_folder(self, version=None, remote = None):
        if version is None:
            version = self.current_version()
        if version is None:
            bin_folder = self.bin_folder
        else:
            bin_folder = self.bin_folder.replace('$version', version)

        # The folder where all the builds are made
        if remote:
            bp = self.get_remote_build_path(node=remote)
        else:
            bp = self.get_build_path()
        return os.path.join(bp,'') + ( os.path.join(bin_folder, '') if bin_folder else '')

    def get_local_bin_path(self, version):
        if version is None:
            version = self.current_version()
        if version is None:
            bin_name = self.bin_name
        else:
            bin_name = self.bin_name.replace('$version', version)
        return self.get_local_bin_folder(version=version) + bin_name

    def get_last_build(self, history: int = 1, stop_at: Build = None, with_results=False, force_fetch=False) -> Build:
        if self.version:
            versions = [self.version]
        else:
            if force_fetch or not self._last_100:
                versions = self.method.get_last_versions(100, force_fetch=force_fetch)
                self._last_100 = versions
            else:
                versions = self._last_100

        last_build = None
        for i, version in enumerate(versions):
            if stop_at and version == stop_at.version:
                if i == 0:
                    return None
                break
            last_build = Build(self, version, self.options.result_path)
            if not with_results or last_build.hasResults():
                if history <= 1:
                    break
                else:
                    history -= 1
            if i > 100:
                last_build = None
                break
        return last_build

    def last_build_before(self, old_build) -> Build:
        return self.get_last_build(stop_at=old_build, history=-1)

    def get_old_results(self, last_graph: Build, num_old: int, test):
        graphs_series = []
        # Todo
        parents = self.method.gitrepo().iter_commits(last_graph.version)
        next(parents)  # The first commit is last_graph itself

        for i, commit in enumerate(parents):  # Get old results for graph
            g_build = Build(self, commit.hexsha[:7], self.options.result_path)
            if not g_build.hasResults(test):
                continue
            g_all_results = g_build.load_results(test)
            graphs_series.append((test, g_build, g_all_results))
            if (i > 100 or len(graphs_series) == num_old):
                break
        return graphs_series

    def current_build(self):
        if self._current_build:
            return self._current_build
        return None

    def current_version(self):
        build = self.current_build()
        if build:
            return build.version
        return Build.get_current_version(self)

    def __str__(self):
        return self.get_reponame()

    @classmethod
    def get_instance(cls, dep, options):
        if dep in cls._repo_cache:
            return cls._repo_cache[dep]
        try:
            repo = Repository(dep, options)
        except FileNotFoundError:
            raise Exception("%s is not a valid repository name !" % (dep))
        cls._repo_cache[dep] = repo
        return repo
