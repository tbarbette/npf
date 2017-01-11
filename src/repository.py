from src.build import Build
from .testie import *
from .variable import is_numeric

import git

repo_variables=['name','branch','configure','url','parent','tags','make']
class Repository:
    configure = '--disable-linuxmodule'
    branch = 'master'
    make = 'make -j12'
    make_clean = 'make clean'
    __gitrepo = None

    def __init__(self, repo):
        self.reponame = repo
        self.tags=[]
        f = open('repo/' + repo + '.repo', 'r')
        for line in f:
            if line.startswith("#"):
                continue
            if not line:
                continue
            s = line.split('=',1)
            val = s[1].strip()
            var = s[0].strip()
            append=False
            if var.endswith('+'):
                var = var[:-1]
                append=True

            if is_numeric(val):
                val = float(val)
                if val.is_integer():
                    val = int(val)
            if not var in repo_variables:
                raise Exception("Unknown variable %s " % var)
            elif var == "parent":
                parent = Repository(val)
                for attr in repo_variables:
                    if not hasattr(parent,attr):
                        continue
                    setattr(self,attr,getattr(parent,attr))
            elif var == "tags":
                self.tags += val.split(',')
                continue

            if append:
                setattr(self,var,getattr(self,var) + " " +val)
            else:
                setattr(self,var,val)

    def checkout(self, branch=None) -> git.Repo:
        """
        Checkout the repo to its folder, fetch if it already exists
        :param branch: An optional branch
        :return:
        """
        repo = self
        if not os.path.exists(repo.reponame):
            os.mkdir(repo.reponame)

        clickpath = repo.reponame + "/build"

        if not branch is None:
            self.branch = branch

        if os.path.exists(clickpath):
            gitrepo = git.Repo(clickpath)
            o = gitrepo.remotes.origin
            o.fetch()
        else:
            gitrepo = git.Repo.clone_from(repo.url, clickpath)
        self.__gitrepo = gitrepo
        return gitrepo

    def gitrepo(self) -> git.Repo:
        if (self.__gitrepo):
            return self.__gitrepo
        else:
            return self.checkout()

    def get_last_build(self, history: int = 0, stop_at: Build = None) -> Build:
        last_build = None
        origin = self.gitrepo().remotes.origin
        origin.fetch()
        for i, commit in enumerate(self.gitrepo().iter_commits('origin/' + self.branch)):
            uuid = commit.hexsha[:7]
            if stop_at and uuid == stop_at.uuid:
                if i == 0:
                    return None
                break
            last_build = Build(self, uuid)
            if last_build.hasResults():
                if history == 0:
                    break
                else:
                    history -= 1
            if i > 100:
                last_build = None
                break
        return last_build

    def last_build_before(self, old_build) -> Build:
        return self.get_last_build(stop_at=old_build,history=-1)

    def get_old_results(self, last_graph:Build, num_old:int, testie:Testie):
        graphs_series = []
        parents = self.gitrepo().iter_commits(last_graph.uuid)
        next(parents)  # The first commit is last_graph itself

        for i, commit in enumerate(parents):  # Get old results for graph
            g_build = Build(self, commit.hexsha[:7])
            if not g_build.hasResults(testie):
                continue
            g_all_results = g_build.readUuid(testie)
            graphs_series.append((testie, g_build, g_all_results))
            if (i > 100 or len(graphs_series) == num_old):
                break
        return graphs_series
