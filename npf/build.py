import os
import subprocess
from collections import OrderedDict
from subprocess import PIPE
from pathlib import Path
import re
from npf import variable, npf
from npf.types.dataset import Run, Dataset
import copy

renametable = {
    'npf.script': 'npf.testie',
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
        self._marker = '.'
        self._line = '-'

    def copy(self):
        return copy.copy(self)

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
            return None
        return data.strip()

    def __result_folder(self):
        return 'results/' + self.repo.get_identifier() + '/'

    def result_path(self, test_name, ext, suffix=''):
        return self.__result_folder() + self.version + '/' + os.path.splitext(test_name)[
            0] + suffix + '.' + ext

    @staticmethod
    def __write_file(fp, val):
        f = open(fp, 'w+')
        f.write(val)
        f.close()

    def __repr__(self):
        return "Build(repo=" + str(self.repo) + ", version=" + self.version + ")"

    def __resultFilename(self, script=None):
        if script:
            return self.__result_folder() + self.version + '/' + script.filename + ".results"
        else:
            return self.__result_folder() + self.version + '.results'

    def writeversion(self, script, all_results: Dataset):
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
                v.append((key + ":" + str(val).replace(':','\:')).replace(',','\,'))
            type_results = []
            for t,r in results.items():
                str_results = []
                if r is None:
                    pass
                else:
                    for val in r:
                        str_results.append(str(val))
                type_results.append(t+':'+(','.join(str_results)))
            f.write(','.join(v) + "={" + '},{'.join(type_results) + "}\n")
        f.close()

    def load_results(self, testie):
        filename = self.__resultFilename(testie)
        if not Path(filename).exists():
            return None
        f = open(filename, 'r')
        all_results = {}
        try:
            for iline,line in enumerate(f):
                variables_data, results_data = line.split('=')

                variables = OrderedDict()

                for v_data in re.split(r'(?<!\\),', variables_data):
                    if v_data.strip():
                        k, v = re.split(r'(?<!\\):', v_data)
                        variables[k] = variable.get_numeric(v) if testie.variables.is_numeric(k) else str(v).replace('\:',':')
                results = {}

                results_data = results_data.strip()[1:-1].split('},{')
                if len(results_data) == 1 and results_data[0].strip() == '':
                    pass
                else:
                    for type, results_type_data in [x.split(':') for x in results_data]:
                        results_type_data = results_type_data.split(',')
                        if len(results_type_data) == 1 and results_type_data[0].strip() == '':
                            type_results = None
                        else:
                            type_results = []
                            for result in results_type_data:
                                type_results.append(float(result.strip()))
                        results[type] = type_results
                all_results[Run(variables)] = results
        except:
            print("Could not parse %s. The program will stop to avoid erasing data. Please correct or delete the file.\nLine %d : %s" % (filename,iline, line))
            raise
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

    def checkout(self,quiet = False):
        if not self.repo.url:
            return True
        if not self.repo.method.checkout(self.version):
            return False
        self.__write_file(self.build_path() + '/.checkout_version', self.version)
        return True


    def is_checkout_needed(self):
        c_ver = Build.__read_file(self.repo.get_build_path() + '/.checkout_version')
        if c_ver is not None and c_ver == self.version:
            return False
        else:
            return True


    def is_compile_needed(self):
        bin_path=npf.replace_path(self.repo.get_bin_path(self.version),build=self)
        if os.path.exists(bin_path) and (
                    Build.get_current_version(self.repo) == self.version):
            return False
        else:
            return True

    def compile(self, quiet = False, show_cmd = False):
        """
        Compile the currently checked out repo, assuming it is currently at self.version
        :return: True upon success, False if not
        """
        if not self.repo.url:
            return True
        pwd = os.getcwd()
        os.chdir(self.build_path())

        for what,command in [("Configuring %s..." % self.version,npf.replace_path(self.repo.configure,build=self)),
                             ("Cleaning %s..." % self.version,npf.replace_path(self.repo.clean,build=self)),
                             ("Building %s..." % self.version,npf.replace_path(self.repo.make,build=self))]:
            if not command:
                continue
            if not quiet:
                print(what)
            if show_cmd and command:
                print(command)
            env = os.environ.copy()
            env.update(self.repo.env)
            p = subprocess.Popen(command, shell=True, stdin=PIPE, stdout=PIPE, stderr=PIPE, env=env)
            output, err = [x.decode() for x in p.communicate()]
            p.wait()
            if not p.returncode == 0:
                print("Aborted (error code %d) !" % p.returncode)
                print("stdout :")
                print(output)
                print("stderr :")
                print(err)
                self.__write_file('.build_version', '')
                os.chdir(pwd)
                return False

        os.chdir(pwd)
        self.__write_file(Build.__get_build_version_path(self.repo), self.version)
        return True

    def build(self, force_build : bool = False, never_build : bool = False, quiet_build : bool = False, show_build_cmd : bool = False, executor=None):
        if force_build or self.is_checkout_needed():
            force_build = True
            if never_build:
                if not quiet_build:
                    print("Warning : will not do test because you disallowed build")
                return False
            if not quiet_build:
                print("Checking out %s" % (self.repo.name))
            if not self.checkout(quiet_build):
                return False
        if force_build or self.is_compile_needed():
            if never_build:
                print("Warning : will not do test because you disallowed build")
            if not quiet_build:
                print("Building %s" % (self.repo.name))
            if not self.compile(quiet_build, show_build_cmd):
                return False
        self.repo._current_build = self
        return True

    def get_bin_folder(self):
        return self.repo.get_bin_folder(self.version)

    @staticmethod
    def get_current_version(repo):
        return Build.__read_file(Build.__get_build_version_path(repo))

    @staticmethod
    def __get_build_version_path(repo):
        return repo.get_build_path() + '/.build_version'
