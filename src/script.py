from subprocess import Popen,PIPE
import os
import sys

from src.section import *

class Script:
    def __init__(self, script, repo, clickpath, quiet = False, show_full = False):
        self.sections = []
        self.files = []
        self.filename = os.path.basename(script)
        self.repo = repo
        self.clickpath = clickpath
        self.quiet = quiet
        self.show_full = show_full
        self.appdir = os.path.dirname(os.path.abspath(sys.argv[0])) + "/"
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
            for k,v in v.iteritems():
                s.content = s.content.replace("$" + k,str(v))
            f.write(s.content)
            f.close()

    def cleanup(self):
        for s in self.files:
            os.remove(s.filename)

    def execute(self):
        p=Popen(self.script.content,stdin=PIPE,stdout=PIPE,stderr=PIPE,shell=True,env={"PATH":self.appdir + self.repo+"/build/bin"})

        output, err = p.communicate(self.stdin.content)
        nr = re.search("RESULT ([0-9.]+)",output.strip())

        if (nr):
            n = float(nr.group(1))
            return n, output, err
        else:
            return False, output, err


