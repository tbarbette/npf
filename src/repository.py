from script import *

repo_variables=['name','branch','configure','url','parent']
class Repository:
    def __init__(self, repo):
        self.reponame = repo
        f = open('repo/' + repo + '.repo', 'r')
        for line in f:
            if line.startswith("#"):
                continue
            if not line:
                continue
            s = line.split('=')
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
                raise Exception("unknown variable %s " % var)
            elif var == "parent":
                parent = Repository(val)
                for attr in dir(parent):
                    if attr.startswith('__') or attr == 'reponame':
                        continue
                    setattr(self,attr,getattr(parent,attr))

            if append:
                setattr(self,var,getattr(self,var) + val)
            else:
                setattr(self,var,val)


