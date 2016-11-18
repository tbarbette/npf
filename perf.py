from subprocess import Popen,PIPE
import sys
import re
import os
import shlex

def is_numeric(s):
    try:
        val = float(s)
    except TypeError:
        return False
    except ValueError:
        return False
    return val

class VariableFactory:
    @staticmethod
    def build(name,valuedata):
        if is_numeric(valuedata):
            return SimpleVariable(name,valuedata)
        result = re.match("\[(-?[0-9]+)([+]|[*])(-?[0-9]+)\]", valuedata)
        if result:
            return RangeVariable(name,int(result.group(1)),int(result.group(3)),result.group(2) == "*")
        raise Exception("Unkown variable type : " + valuedata)


class SimpleVariable:
    def __init__(self,name,value):
        self.name = name
        self.value = value

    def makeValues(self):
        return [{self.name : self.value}]

class RangeVariable:
    def __init__(self,name,valuestart,valueend,log):
        if (valuestart > valueend):
            self.a = valueend
            self.b = valuestart
        else:
            self.a = valuestart
            self.b = valueend
        self.name = name
        self.log = log

    def makeValues(self):
        vs=[]
        if self.log:
            i=self.a
            while i <= self.b:
                vs.append({self.name : i})
                if i==0:
                    i = 1
                else:
                    i*=2
        else:
            for i in range(self.a,self.b + 1):
                vs.append({self.name : i})
        return vs

class SectionFactory:
    @staticmethod
    def build(perf, data):
        s=Section(data[0].rstrip())
        if (s.name == 'file'):
            s.filename = data[1].rstrip()
            perf.files.append(s)
        elif (len(data) > 1):
            raise Exception("Only file section takes arguments (" + s.name +" has argument " + data[1] + ")");
        elif (hasattr(perf,s.name)):
            raise Exception("Only one section of type " + s.name + " is allowed")
        else:
            setattr(perf,s.name,s)
        return s

class Section:
    def __init__(self, name):
        self.name = name
        self.content = ''

class Perf:
    def __init__(self, script):
        self.sections = []
        self.files = []
        self.filename = os.path.basename(script)
        section=''
        f = open(script, 'r')
        for line in f:
            if line.startswith("#"):
                continue
            elif line.startswith("%"):
                if (section):
                    self.sections.append(section)
                result = line[1:].split(' ')
                section = SectionFactory.build(self, result)
            elif (not section):
                raise Exception("Bad syntax, file must start by a section");
            else:
                section.content += line
        if (not hasattr(self,"info")):
            self.info = Section("info")
            self.info.content = self.filename

    def expandvariables(self):
        if (not hasattr(self,"variables")):
            self.variables = [dict()]
        else:
            var_section = self.variables
            self.variables=[dict()]
            vs=[]
            for line in var_section.content.split("\n"):
                if not line:
                    continue
                var = line.split('=')
                vs.append(VariableFactory.build(var[0],var[1]))

            for v in vs:
                newList=[]
                for nvalue in v.makeValues():
                    for ovalue in self.variables:
                        z = ovalue.copy()
                        z.update(nvalue)
                        newList.append(z)
                self.variables = newList

    def createfiles(self, v):
        for s in self.files:
            f = open(s.filename,"w")
            for k,v in v.iteritems():
                s.content = s.content.replace("$" + k,str(v))
            f.write(s.content)
            f.close()

    def cleanup(self):
        for s in self.files:
            os.remove(s.filename)

    def resultFilename(self, repo, uuid, scriptname, vs):
        return repo + '/results/' + uuid + '/' +  (scriptname + '_'.join([ key + "-" + str(value) for key, value in vs.items()]));

def usage():
    print "Usage : " + sys.argv[0] + " script repo uuid"
    print "     script : path to script"
    print "     repo : name of the repo/group of builds"
    print "     uuid : build id"

def main(argv=sys.argv):

    if len(argv) < 4:
        usage();
    script = Perf(argv[1])
    repo=argv[2]
    uuid=argv[3]
    clickpath=repo+"/build"

    print script.info.content.strip()
    script.expandvariables()
    for v in script.variables:
        print v
        script.createfiles(v)
        p=Popen(script.script.content,stdin=PIPE,stdout=PIPE,stderr=PIPE,shell=True,env={"PATH":repo+"/build/bin"})
        output, err = p.communicate("")
        nr = re.match("RESULT ([0-9.]+)",output.strip())
        if (nr):
            n = float(nr.group(1))
            filename = script.resultFilename(repo,uuid,script.filename,v)
            try:
                os.makedirs(os.path.dirname(filename))
            except OSError:
                pass
            f = open(filename,'w+')
            f.write(str(n))
            f.close
        else:
            print "Test did not show result? stdout and stderr :"
            print output
            print err
    script.cleanup()


if __name__ == "__main__":
    main()
