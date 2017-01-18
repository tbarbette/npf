import os
import subprocess
from collections import OrderedDict
from subprocess import PIPE
import git

from src import variable
from src.testie import Run, Testie

renametable = {
    'src.script': 'src.testie',
}


def mapname(name):
    if name in renametable:
        return renametable[name]
    return name


def mapped_load_global(self):
    module = mapname(self.readline()[:-1])
    name = mapname(self.readline()[:-1])
    klass = self.find_class(module, name)
    self.append(klass)


class Build:
    def __init__(self, repo, uuid):
        self.n_tests = 0
        self.n_passed = 0
        self.repo = repo
        self.uuid = uuid
        self.path = self.repo.reponame + "/build/"

    def __read_file(self, fp):
        try:
            with open(fp, 'r') as myfile:
                data = myfile.read().replace('\n', '')
        except FileNotFoundError:
            return False
        return data.strip()

    def result_path(self, testie, type,suffix=''):
        return self.repo.reponame + '/results/' + self.uuid + '/' + os.path.splitext(testie.filename)[
            0] + suffix + '.' + type

    @staticmethod
    def __write_file(fp, val):
        f = open(fp, 'w+')
        f.write(val)
        f.close()

    def is_build_needed(self):
        gitrepo = git.Repo(self.click_path())
        if gitrepo.head.commit.hexsha[:7] != self.uuid:
            return True
        if os.path.exists(self.click_path() + '/bin/click') and (self.__read_file(self.click_path() + '/.current_build') == self.uuid):
            return False
        else:
            return True

    def build_if_needed(self):
        gitrepo = git.Repo(self.click_path())
        if gitrepo.head.commit.hexsha[:7] != self.uuid:
            self.build()
        if not os.path.exists(self.click_path() + '/bin/click') or \
                not (self.__read_file(self.click_path() + '/.current_build') == self.uuid):
            return self.compile()
        return True

    def compile(self):
        """
        Compile the currently checked out repo, assuming it is currently at self.uuid
        :return: True upon success, False if not
        """
        pwd = os.getcwd()
        os.chdir(self.click_path())

        for what,command in [("Configuring %s..." % self.uuid,'./configure ' + self.repo.configure),
                             ("Cleaning %s..." % self.uuid,self.repo.make_clean),
                             ("Building %s..." % self.uuid,self.repo.make)]:
            print(what)
            p = subprocess.Popen(command, shell=True, stdin=PIPE, stdout=PIPE, stderr=PIPE)
            output, err = [x.decode() for x in p.communicate()]
            p.wait()
            if not p.returncode == 0:
                print("Aborted (error code %d) !" % p.returncode)
                print("stdout :")
                print(output)
                print("stderr :")
                print(err)
                self.__write_file('.current_build', '')
                os.chdir(pwd)
                return False

        os.chdir(pwd)
        self.__write_file(self.click_path() + '/.current_build', self.uuid)
        return True

    def __repr__(self):
        return "Build(repo=" + str(self.repo) + ", uuid=" + self.uuid + ")"

    def __resultFilename(self, script=None):
        if script:
            return self.repo.reponame + '/results/' + self.uuid + '/' + script.filename + ".results";
        else:
            return self.repo.reponame + '/results/' + self.uuid + '.results';

    def writeUuid(self, script, all_results):
        filename = self.__resultFilename(script)
        try:
            if not os.path.exists(os.path.dirname(filename)):
                os.makedirs(os.path.dirname(filename))
        except OSError:
            print("Error : could not create %s" % os.path.dirname(filename))
        f = open(filename, 'w+')
        f.seek(0)
        for run, results in all_results.items():
            v = []
            for key, val in sorted(run.variables.items()):
                if type(val) is tuple:
                    val = val[1]
                v.append(key + ":" + str(val))
            str_results = []
            if results is None:
                pass
            else:
                for r in results:
                    str_results.append(str(r))
            f.write(','.join(v) + "=" + ','.join(str_results) + "\n")
        f.close

    def readUuid(self, testie: Testie):
        filename = self.__resultFilename(testie)
        f = open(filename, 'r')
        all_results = {}
        for line in f:
            variables_data, results_data = [x.split(',') for x in line.split('=')]
            variables = OrderedDict()
            for v_data in variables_data:
                k, v = v_data.split(':')
                variables[k] = variable.get_numeric(v)
            results = []
            if len(results_data) == 1 and results_data[0].strip() == '':
                results = None
            else:
                for result in results_data:
                    results.append(float(result.strip()))
            all_results[Run(variables)] = results
        f.close
        return all_results

    def hasResults(self, script=None):
        return os.path.exists(self.__resultFilename(script))

    def writeResults(self):
        open(self.__resultFilename(), 'a').close()

    def click_path(self):
        return self.repo.reponame + "/build"

    def checkout(self):
        gitrepo = git.Repo(self.click_path())
        ref = gitrepo.commit(self.uuid)
        gitrepo.git.checkout(ref, force=True)
        self.__write_file(self.click_path() + '/.current_build', '')
        return True

    def build(self):
        if not self.checkout():
            return False
        if not self.compile():
            return False
        return True
