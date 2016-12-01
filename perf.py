from subprocess import Popen,PIPE
import sys
import re
import os
import shlex
import argparse
import math

from src.section import *
from src.variable import *

class Perf:
    def __init__(self, script, repo, clickpath, quiet = False, show_full = False):
        self.sections = []
        self.files = []
        self.filename = os.path.basename(script)
        self.repo = repo
        self.clickpath = clickpath
        self.quiet = quiet
        self.show_full = show_full
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

    def resultFilename(self, uuid, vs):
        return self.repo + '/results/' + uuid + '/' + (self.filename + '_'.join([ key + "-" + str(value) for key, value in vs.items()]));

    def writeUuid(self, uuid, vs, n):
        filename = self.resultFilename(uuid,vs)
        try:
            os.makedirs(os.path.dirname(filename))
        except OSError:
            pass
        f = open(filename,'w+')
        f.write(str(n))
        f.close

    def readUuid(self, uuid, vs):
        filename = self.resultFilename(uuid,vs)
        f = open(filename,'r')
        n = float(f.readline())
        f.close
        return n

    def __execute(self):
        p=Popen(self.script.content,stdin=PIPE,stdout=PIPE,stderr=PIPE,shell=True,env={"PATH":self.__curdir + self.repo+"/build/bin"})

        output, err = p.communicate(self.stdin.content)
        nr = re.search("RESULT ([0-9.]+)",output.strip())

        if (self.show_full):
            print 'stdout:'
            print output
            print 'stderr:'
            print err

        if (nr):
            n = float(nr.group(1))
            return n
        else:
            return False


    def run(self, uuid, old_uuids=[]):
        script = self
        returncode=0
        self.__curdir = os.path.dirname(os.path.realpath(__file__)) + "/"

        for v in self.variables:
            if len(v):
                print v
            script.createfiles(v)
            result = []
            for i in range(self.config.n_runs):
                n = self.__execute()
                if n == False:
                    result = False
                    break
                result.append(n)

            if result:
                n = sum(result)/float(len(result))
                script.writeUuid(uuid,v,n)

                for ouuid in old_uuids:
                    lastn = script.readUuid(ouuid,v)
                    diff=abs(lastn - n) / float(lastn)
                    ok = False
                    if (diff > script.config.acceptable):
                        if (script.config.unacceptable_n_runs > 0):
                            if not self.quiet:
                                print "Outside acceptable range ("+str(diff*100)+"%). Running supplementary tests..."
                            for i in range(self.config.unacceptable_n_runs):
                                n = self.__execute()
                                if n == False:
                                    result = False
                                    break
                                result.append(n)
                            if result:
                                result.sort()
                                rem=int(math.floor(len(result) / 4))
                                for i in range(rem):
                                    result.pop()
                                    result.pop(0)
                                n = sum(result)/float(len(result))
                                diff=abs(lastn - n) / float(lastn)
                                ok = diff <= script.config.acceptable
                    else:
                        ok = True

                    if not ok:
                        print "ERROR: Test " + script.filename + " is outside acceptable margin between " +uuid+ " and " + ouuid + " : difference of " + str(diff*100) + "% !"
                        returncode=1
                    else:
                        print "Acceptable difference of " + str(diff * 100) + "%"

            else:
                print "Test did not show result? stdout :"
                print output
                print "stderr :"
                print err
        script.cleanup()
        return returncode

def main(argv=sys.argv):
    parser = argparse.ArgumentParser(description='Click Performance Executor')
    parser.add_argument('--show-full', help='Show full execution results', dest='show_full', action='store_true')

    parser.add_argument('--quiet', help='Quiet mode', dest='quiet', action='store_true')
    parser.add_argument('script', metavar='script', type=str, nargs=1, help='path to script');
    parser.add_argument('repo', metavar='repo', type=str, nargs=1, help='name of the repo/group of builds');
    parser.add_argument('uuid', metavar='uuid', type=str, nargs=1, help='build id');
    parser.add_argument('old_uuids', metavar='old_uuids', type=str, nargs='*', help='old build id to compare against');
    parser.set_defaults(show_full=False)
    parser.set_defaults(quiet=False)
    args = parser.parse_args();

    repo=args.repo[0]
    uuid=args.uuid[0]
    clickpath=repo+"/build"
    old_uuids=args.old_uuids

    script = Perf(args.script[0],repo,clickpath,quiet=args.quiet,show_full=args.show_full)

    print script.info.content.strip()

    returncode = script.run(uuid, old_uuids);
    sys.exit(returncode)


if __name__ == "__main__":
    main()
