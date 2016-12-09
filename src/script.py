from subprocess import Popen,PIPE
import os
import sys

from src.section import *
class Run:
    def __init__(self, variables):
        self.variables = variables

    def format_variables(self,hide={}):
        s=[]
        for k,v in self.variables.items():
            if k in hide : continue
            if type(v) is tuple:
                s.append('%s = %s' % (k,v[1]))
            else:
                s.append('%s = %s' % (k,v))
        return ', '.join(s)

    def print_variable(self,k):
        v = self.variables[k]
        if type(v) is tuple:
            return v[1]
        else:
            return v

    def __eq__(self, o):
        return self.variables.__eq__(o.variables)

    def __hash__(self):
        return self.format_variables().__hash__()

    def __repr__(self):
        return "Run(" + self.format_variables() + ")"

    def __lt__(self, o):
        for k,v in self.variables.items():
            if not k in o.variables: return False
            if v < o.variables[k]:
                return True
            if v > o.variables[k]:
                return False
        return False

class Script:
    def __init__(self, script, clickpath, quiet = False, show_full = False, tags=[]):
        self.sections = []
        self.files = []
        self.filename = os.path.basename(script)
        self.clickpath = clickpath
        self.quiet = quiet
        self.show_full = show_full
        self.appdir = os.path.dirname(os.path.abspath(sys.argv[0])) + "/"
        self.tags = tags
        section=''

        f = open(script, 'r')
        for line in f:
            if line.startswith("#"):
                continue
            elif line.startswith("%"):
                result = line[1:].split(' ')
                section = SectionFactory.build(self, result)
                self.sections.append(section)
            elif (not section):
                raise Exception("Bad syntax, file must start by a section");
            else:
                section.content += line

        if (not hasattr(self,"info")):
            self.info = Section("info")
            self.info.content = self.filename
            self.sections.append(self.info)

        if (not hasattr(self,"stdin")):
            self.stdin = Section("stdin")
            self.sections.append(self.stdin)

        if (not hasattr(self,"variables")):
            self.variables = SectionVariable()
            self.sections.append(self.variables)

        for section in self.sections:
            section.finish(self)

    def createfiles(self, v):
        for s in self.files:
            f = open(s.filename,"w")
            p = s.content
            for k,v in v.items():
                if type(v) is tuple:
                    p = p.replace("$" + k,str(v[0]))
                else:
                    p = p.replace("$" + k,str(v))
            f.write(p)
            f.close()

    def cleanup(self):
        for s in self.files:
            os.remove(s.filename)

    def execute(self,build,v,n_runs=1):
        self.createfiles(v)
        results=[]
        for i in range(n_runs):
            p=Popen(self.script.content,stdin=PIPE,stdout=PIPE,stderr=PIPE,shell=True,env={"PATH":self.appdir + build.repo.reponame+"/build/bin:" + os.environ["PATH"]})

            output, err = [x.decode() for x in p.communicate(self.stdin.content, timeout=self.config["timeout"])]
            nr = re.search("RESULT ([0-9.]+)",output.strip())

            if (nr):
                n = float(nr.group(1))
                results.append(n)
            else:
                print("Could not find result !")
                print("stdout:")
                print(output)
                print("stderr:")
                print(err)
                return False, output, err

        self.cleanup()
        return results, output, err


    def execute_all(self, build):
        all_results={}
        for variables in self.variables:
            run = Run(variables)
            if not self.quiet:
                print(run.format_variables(self.config["var_hide"]))
            results,output,err = self.execute(build,variables,self.config["n_runs"])
            if not self.quiet:
                print(results)
            if self.show_full:
                print("stdout:")
                print(output)
                print("stderr:")
                print(err)
            if results:
                all_results[run] = results
            else:
                all_results[run] = None
        return all_results

