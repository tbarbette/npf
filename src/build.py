import os
import subprocess
from collections import OrderedDict
from subprocess import PIPE
from pathlib import Path

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
    def __init__(self, repo, version):
        self.n_tests = 0
        self.n_passed = 0
        self.repo = repo
        self.version = version
        self._pretty_name = None

    def pretty_name(self):
        if self._pretty_name:
            return self._pretty_name
        else:
            return self.version

    @staticmethod
    def __read_file(fp):
        try:
            with open(fp, 'r') as myfile:
                data = myfile.read().replace('\n', '')
        except FileNotFoundError:
            return False
        return data.strip()

    def result_path(self, testie, type,suffix=''):
        return self.repo.reponame + '/results/' + self.version + '/' + os.path.splitext(testie.filename)[
            0] + suffix + '.' + type

    @staticmethod
    def __write_file(fp, val):
        f = open(fp, 'w+')
        f.write(val)
        f.close()

    def __repr__(self):
        return "Build(repo=" + str(self.repo) + ", version=" + self.version + ")"

    def __resultFilename(self, script=None):
        if script:
            return self.repo.reponame + '/results/' + self.version + '/' + script.filename + ".results";
        else:
            return self.repo.reponame + '/results/' + self.version + '.results';

    def writeversion(self, script, all_results):
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
        f.close()

    def load_results(self, testie: Testie):
        filename = self.__resultFilename(testie)
        if not Path(filename).exists():
            return None
        f = open(filename, 'r')
        all_results = {}
        for line in f:
            variables_data, results_data = [x.split(',') for x in line.split('=')]
            variables = OrderedDict()
            for v_data in variables_data:
                if v_data:
                    k, v = v_data.split(':')
                    variables[k] = variable.get_numeric(v) if testie.variables.is_numeric(k) else str(v)
            results = []
            if len(results_data) == 1 and results_data[0].strip() == '':
                results = None
            else:
                for result in results_data:
                    results.append(float(result.strip()))
            all_results[Run(variables)] = results
        f.close()
        return all_results

    def hasResults(self, script=None):
        return os.path.exists(self.__resultFilename(script))

    def writeResults(self):
        filename = self.__resultFilename()
        if not os.path.exists(os.path.dirname(filename)):
            os.makedirs(os.path.dirname(filename))
        open(filename, 'a').close()

    def build_path(self):
        return self.repo.get_build_path()

    def checkout(self):
        if not self.repo.url:
            return True
        if not self.repo.method.checkout(self.version):
            return False
        self.__write_file(self.build_path() + '/.checkout_version', self.version)
        return True


    def is_checkout_needed(self):
        if Build.__read_file(self.repo.get_build_path() + '/.checkout_version') == self.version:
            return False
        else:
            return True

    def is_compile_needed(self):
        if os.path.exists(self.repo.get_bin_path(self.version)) and (
                    Build.__read_file(self.repo.get_build_path() + '/.build_version') == self.version):
            return False
        else:
            return True

    def compile(self):
        """
        Compile the currently checked out repo, assuming it is currently at self.version
        :return: True upon success, False if not
        """
        if not self.repo.url:
            return True
        pwd = os.getcwd()
        os.chdir(self.build_path())

        for what,command in [("Configuring %s..." % self.version,self.repo.configure.replace('$version',self.version)),
                             ("Cleaning %s..." % self.version,self.repo.clean.replace('$version',self.version)),
                             ("Building %s..." % self.version,self.repo.make.replace('$version',self.version))]:
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
        self.__write_file(self.repo.get_build_path()  + '/.build_version', self.version)
        return True

    def build(self, force_build : bool, never_build : bool = False):
        if force_build or self.is_checkout_needed():
            force_build = True
            if never_build:
                print("Warning : will not do test because you disallowed build")
                return False
            print("Checking out %s" % (self.repo.name))
            if not self.checkout():
                return False
        if force_build or self.is_compile_needed():
            if never_build:
                print("Warning : will not do test because you disallowed build")
            print("Building %s" % (self.repo.name))
            if not self.compile():
                return False
        return True

    def get_bin_folder(self):
        return self.repo.get_bin_folder(self.version)