import os
import math

class Regression:
    def __init__(self, script, show_full=False):
        self.script = script
        self.show_full = show_full

    def resultFilename(self, uuid, vs):
        return self.script.repo.reponame + '/results/' + uuid + '/' + (self.script.filename + '_'.join([ key + "-" + str(value) for key, value in vs.items()]));

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
        try:
            f = open(filename,'r')
            n = float(f.readline())
            f.close
        except IOError:
            return False
        return n

    def run(self, uuid, old_uuids=[]):
        script = self.script
        returncode=0
        for v in script.variables:
            if len(v):
                print v
            script.createfiles(v)
            result = []
            for i in range(script.config.n_runs):
                n,output,err = script.execute()
                if n == False:
                    result = False
                    break
                result.append(n)

            if result:
                if (self.show_full):
                    print 'stdout:'
                    print output
                    print 'stderr:'
                    print err
                n = sum(result)/float(len(result))
                self.writeUuid(uuid,v,n)

                for ouuid in old_uuids:
                    lastn = self.readUuid(ouuid,v)
                    diff=abs(lastn - n) / float(lastn)
                    ok = False
                    if (diff > script.config.acceptable):
                        if (script.config.unacceptable_n_runs > 0):
                            if not script.quiet:
                                print "Outside acceptable range ("+str(diff*100)+"%). Running supplementary tests..."
                            for i in range(script.config.unacceptable_n_runs):
                                n,output,err = script.execute()
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

