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

    def checkout(self, branch=None):
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

    def gitrepo(self):
        if (self.__gitrepo):
            return self.__gitrepo
        else:
            return self.checkout()

