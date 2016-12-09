import os
import pickle

class Build:
    def __init__(self, repo, uuid):
        self.repo = repo
        self.uuid = uuid
        self.path = self.repo.reponame+"/build/"

    def __repr__(self):
        return "Build(repo=" + str(self.repo)  + ", uuid=" + self.uuid +")"

    def __resultFilename(self, script):
        return self.repo.reponame + '/results/' + self.uuid + '/' + script.filename + ".results";

    def writeUuid(self, script, results):
        filename = self.__resultFilename(script)
        try:
            os.makedirs(os.path.dirname(filename))
        except OSError:
            pass
        f = open(filename,'wb+')
#        for variables,result in results:
#            v=""
#            for key,values in variables:
#                v += key + "=" + str(value)
#            f.write(v+"=")
        pickle.dump(results,f)
        f.close

    def readUuid(self, script):
        filename = self.__resultFilename(script)
        f = open(filename,'rb')
        results = pickle.load(f,)
        f.close
        return results

