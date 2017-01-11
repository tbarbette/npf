from .variable import *
from collections import OrderedDict

sections = ['info', 'config', 'variables', 'script', 'file', 'require']


class SectionFactory:
    @staticmethod
    def build(testie, data):
        """
        Create a section from a given header
        :param testie: The parent script
        :param data: Array containing the section name and possible arguments
        :return: A Section object
        """
        sectionName = data[0].rstrip()
        if not sectionName in sections:
            raise Exception("Unknown section %s" % sectionName);
        if sectionName == 'file':
            s = SectionFile(data[1].rstrip())
        elif sectionName == 'script':
            s = SectionScript()
            if len(data) > 1:
                s.slave = data[1].rstrip()
        elif len(data) > 1:
            raise Exception("Only file section takes arguments (" + s.name + " has argument " + data[1] + ")");
        elif hasattr(testie, sectionName):
            raise Exception("Only one section of type " + s.name + " is allowed")
        elif sectionName == 'variables':
            s = SectionVariable()
            setattr(testie, s.name, s)
        elif sectionName == 'config':
            s = SectionConfig()
            setattr(testie, s.name, s)
        elif sectionName == 'require':
            s = SectionRequire()
            setattr(testie, s.name, s)
        else:
            s = Section(sectionName)
            setattr(testie, s.name, s)
        return s


class Section:
    def __init__(self, name):
        self.name = name
        self.content = ''

    def finish(self, testie):
        pass


class SectionScript(Section):
    def __init__(self, slave='local'):
        self.name = 'script'
        self.content = ''
        self.slave = 'local'

    def finish(self, script):
        script.scripts.append(self)


class SectionFile(Section):
    def __init__(self, filename):
        self.name = 'file'
        self.content = ''
        self.filename = filename

    def finish(self, testie):
        testie.files.append(self)

class SectionRequire(Section):
    def __init__(self):
        self.name = 'require'
        self.content = ''

    def finish(self, testie):
        pass

class BruteVariableExpander:
    """Expand all variables building the full
    matrix first."""

    def __init__(self, vlist):
        self.expanded = [OrderedDict()]
        for k, v in vlist.items():
            newList = []
            for nvalue in v.makeValues():
                for ovalue in self.expanded:
                    z = ovalue.copy()
                    z.update({k: nvalue})
                    newList.append(z)
            self.expanded = newList
        self.it = self.expanded.__iter__()

    def __next__(self):
        return self.it.__next__()


class SectionVariable(Section):
    def __init__(self):
        self.name = 'variables'
        self.content = ''
        self.vlist = OrderedDict()

    def replace_all(self, value):
        """Return a list of all possible replacement in values for each combination of variables"""
        statics = self.statics()
        if len(statics):
            pattern = re.compile("\$(" + "|".join(statics.keys()) + ")")
            value = pattern.sub(lambda m: statics[re.escape(m.group(0))], value)

        dynamics = self.dynamics()
        pattern = re.compile("\$(" + "|".join(dynamics.keys()) + ")")
        values = []
        for variables in BruteVariableExpander(dynamics).it:
            nvalue = pattern.sub(lambda m: str(variables[re.escape(m.group(1))]), value)
            values.append(nvalue)
        return values

    def __iter__(self):
        return BruteVariableExpander(self.vlist)

    def dynamics(self):
        """List of non-constants variables"""
        dyn = OrderedDict()
        for k, v in self.vlist.items():
            if v.count() > 1: dyn[k] = v
        return dyn

    def statics(self):
        """List of constants variables"""
        dyn = OrderedDict()
        for k, v in self.vlist.items():
            if v.count() <= 1: dyn[k] = v
        return dyn

    def finish(self, testie):
        for line in self.content.split("\n"):
            try:
                if not line:
                    continue
                pair = line.split('=', 1)
                var = pair[0].split(':')

                if len(var) == 1:
                    var = var[0]
                else:
                    if (var[0] in testie.tags) or (var[0].startswith('-') and not var[0][1:] in testie.tags):
                        var = var[1]
                    else:
                        continue
                self.vlist[var] = VariableFactory.build(var, pair[1], self)
            except:
                print("Error parsing line %s" % line)
                raise
        self.vlist = OrderedDict(sorted(self.vlist.items()))

    def dtype(self):
        formats=[]
        names=[]
        for k, v in self.vlist.items():
            f = v.format()
            formats.append(f)
            names.append(k)
        return dict(names = names, formats = formats)



class SectionConfig(SectionVariable):
    def __add(self, var, val):
        self.vlist[var] = SimpleVariable(var, val)

    def __add_list(self, var, list):
        self.vlist[var] = ListVariable(var, list)

    def __init__(self):
        self.name = 'config'
        self.content = ''
        self.vlist = {}
        self.__add("accept_outliers_mult", 1)
        self.__add("accept_variance", 1)
        self.__add("timeout", 300)
        self.__add("acceptable", 0.01)
        self.__add("n_runs", 1)
        self.__add("n_retry", 0)
        self.__add("n_supplementary_runs", 3)
        self.__add("var_names", {})
        self.__add("var_unit", {"result": "BPS"})
        self.__add("legend_loc", "best")
        self.__add("var_hide", {})
        self.__add("var_log", [])
        self.__add_list("require_tags", [])

    def var_name(self, key):
        if key in self["var_names"]:
            return self["var_names"][key]
        else:
            return key

    def get_list(self,key):
        var = self.vlist[key]
        v = var.makeValues()
        return v

    def __contains__(self, key):
        return key in self.vlist

    def __getitem__(self, key):
        var = self.vlist[key]
        v = var.makeValues()
        if type(v) is list and len(v) == 1:
            return v[0]
        else:
            return v

    def __setitem__(self, key, val):
        self.__add(key, val)
