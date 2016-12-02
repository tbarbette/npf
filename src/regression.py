import os
import math
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

graphcolor = ['b','g','r','c','m','y']

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
        series = []
        axis = []
        for i in range(len(old_uuids) + 1):
            axis.append([])
        for v in script.variables:
            if len(v):
                print v
            script.createfiles(v)
            result = []
            for i in range(script.config["n_runs"]):
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
                series.append(v)
                axis[0].append(n)
                for i,ouuid in enumerate(old_uuids):
                    lastn = self.readUuid(ouuid,v)
                    axis[i + 1].append(lastn);
                    if lastn and i == 0:
                        diff=abs(lastn - n) / float(lastn)
                        ok = False
                        if (diff > script.config["acceptable"]):
                            if (script.config["unacceptable_n_runs"] > 0):
                                if not script.quiet:
                                    print "Outside acceptable range ("+str(diff*100)+"%). Running supplementary tests..."
                                for i in range(script.config["unacceptable_n_runs"]):
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
                                    axis[0][-1] = n
                                    self.writeUuid(uuid,v,n)
                                    diff=abs(lastn - n) / float(lastn)
                                    ok = diff <= script.config["acceptable"]
                        else:
                            ok = True

                        if not ok:
                            print "ERROR: Test " + script.filename + " is outside acceptable margin between " +uuid+ " and " + ouuid + " : difference of " + str(diff*100) + "% !"
                            returncode=1
                        else:
                            print "Acceptable difference of " + str(diff * 100) + "%"
                    elif not lastn:
                        print "No old values for this test for uuid %s (new=%f)." % (ouuid, n)

            else:
                print "Test did not show result? stdout :"
                print output
                print "stderr :"
                print err
        script.cleanup()

        uuids= [uuid] + old_uuids
        ss=[]

        dyns = script.variables.dynamics()
        ndyn = len(dyns)

        if ndyn == 0:
            ax=[]
            for a in axis:
                ax.append(a[0])
            plt.bar(range(len(uuids)),ax,label=uuids[i],color=graphcolor[i])
            key = "uuid"
            plt.xticks(np.arange(len(uuids)) + 0.5,uuids, rotation='vertical' if (len(uuids) > 10) else 'horizontal')
        elif ndyn==1:
            key = dyns.keys[0]

            for serie in series:
                ss.append(str(serie[key]))


            for i,ax in enumerate(axis):
                plt.plot(ax,label=uuids[i])
            plt.xticks(np.arange(len(series)),ss, rotation='vertical',)
            plt.legend()
        else:
            width = (1-0.2) / len(uuids)
            ind = np.arange(len(series))

            for i,a in enumerate(axis):
                plt.bar(0.1 + ind + (i * width),a,width, label=str(uuids[i]),color=graphcolor[i])
            key = "uuid"

            for serie in series:
                s = []
                for k,v in serie.iteritems():
                    if k in dyns:
                        s.append("%s = %s" % (self.script.config.varname(k), str(v)))
                ss.append(','.join(s))

            plt.xticks(0.1 + ind + width, ss, rotation='vertical' if (len(ss) > 5) else 'horizontal')
            if (ndyn > 0):
                plt.legend()
        plt.tight_layout()


        plt.xlabel(self.script.config.varname(key))

        if ("result" in self.script.config["varnames"]):
            plt.ylabel(self.script.config["varnames"]["result"])

        plt.title(self.script.config["title"])
        graphname = self.script.repo.reponame + '/results/' + uuid + '/'+ os.path.splitext(self.script.filename)[0] + '.png'
        plt.savefig(graphname)
        print "Graph of test written to %s" % graphname
        return returncode

