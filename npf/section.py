import ast

from typing import List, Set

from npf import npf
from npf.node import Node
from npf.repository import Repository
from .variable import *
from collections import OrderedDict

from asteval import Interpreter


class SectionFactory:
    varPattern = "([a-zA-Z0-9_:-]+)[=](" + Variable.VALUE_REGEX + ")?"
    namePattern = re.compile(
        "^(?P<tags>[a-zA-Z0-9,_-]+[:])?(?P<name>info|config|variables|late_variables|file (?P<fileName>[a-zA-Z0-9_.-]+)|require|"
        "import(:?[@](?P<importRole>[a-zA-Z0-9]+))?[ \t]+(?P<importModule>" + Variable.VALUE_REGEX + ")(?P<importParams>([ \t]+" +
        varPattern + ")+)?|"
                     "(:?script|init)(:?[@](?P<scriptRole>[a-zA-Z0-9]+))?(?P<scriptParams>([ \t]+" + varPattern + ")*))$")

    @staticmethod
    def build(testie, data):
        """
        Create a section from a given header
        :param testie: The parent script
        :param data: Array containing the section name and possible arguments
        :return: A Section object
        """
        matcher = SectionFactory.namePattern.match(data)
        if not matcher:
            raise Exception("Unknown section line '%s'" % data)

        if matcher.group('tags') is not None:
            tags = matcher.group('tags')[:-1].split(',')
        else:
            tags = []

        for tag in tags:
            if tag.startswith('-'):
                if tag[1:] in testie.tags:
                    return SectionNull()
            else:
                if not tag in testie.tags:
                    return SectionNull()
        sectionName = matcher.group('name')

        if sectionName.startswith('import'):
            params = matcher.group('importParams')
            module = matcher.group('importModule')
            params = dict(re.findall(SectionFactory.varPattern, params)) if params else {}
            s = SectionImport(matcher.group('importRole'), module, params)
            return s

        if sectionName.startswith('script') or sectionName.startswith('init'):
            params = matcher.group('scriptParams')
            params = dict(re.findall(SectionFactory.varPattern, params)) if params else {}
            s = SectionScript(matcher.group('scriptRole'), params)
            if sectionName.startswith('init'):
                s.init = True
            return s

        if matcher.group('scriptParams') is not None:
            raise Exception("Only script sections takes arguments (" + sectionName + " has argument " +
                            matcher.groups("params") + ")")

        if sectionName.startswith('file'):
            s = SectionFile(matcher.group('fileName').strip())
            return s
        elif sectionName == 'require':
            s = SectionRequire()
            return s
        if hasattr(testie, sectionName):
            raise Exception("Only one section of type " + sectionName + " is allowed")

        if sectionName == 'variables':
            s = SectionVariable()
        elif sectionName == 'late_variables':
            s = SectionLateVariable()
        elif sectionName == 'config':
            s = SectionConfig()
        elif sectionName == 'info':
            s = Section(sectionName)
        setattr(testie, s.name, s)
        return s


class Section:
    def __init__(self, name):
        self.name = name
        self.content = ''

    def get_content(self):
        return self.content

    def finish(self, testie):
        pass


class SectionNull(Section):
    def __init__(self, name='null'):
        super().__init__(name)


class SectionScript(Section):
    def __init__(self, role=None, params=None):
        super().__init__('script')
        if params is None:
            params = {}
        self.params = params
        self._role = role
        self.init = False

    def get_role(self):
        return self._role

    def get_type(self):
        return "init" if self.init else "script"

    def finish(self, testie):
        testie.scripts.append(self)

    def delay(self):
        return float(self.params.get("delay", 0))

    def get_deps_repos(self, options) -> List[Repository]:
        repos = []
        for dep in self.get_deps():
            repos.append(Repository.get_instance(dep, options))
        return repos

    def get_deps(self) -> Set[str]:
        deps = set()
        if not "deps" in self.params:
            return deps
        for dep in self.params["deps"].split(","):
            deps.add(dep)
        return deps


class SectionImport(Section):
    def __init__(self, role=None, module=None, params=None):
        super().__init__('import')
        if params is None:
            params = {}
        self.params = params
        if module is not None and module is not '':
            self.module = 'tests/module/' + module
        else:
            if not 'testie' in params:
                raise Exception("%import section must define a module name or a testie=[path] to import")
            self.module = params['testie']
            del params['testie']

        self._role = role

    def get_role(self):
        return self._role

    def finish(self, testie):
        if self.get_content().strip() != '':
            raise Exception("%import section does not support any content")
        testie.imports.append(self)


class SectionFile(Section):
    def __init__(self, filename):
        super().__init__('file')
        self.content = ''
        self.filename = filename

    def finish(self, testie):
        testie.files.append(self)


class SectionRequire(Section):
    def __init__(self):
        super().__init__('require')
        self.content = ''

    def role(self):
        # For now, require is only on one node, the default one
        return 'default'

    def finish(self, testie):
        testie.requirements.append(self)


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
    def __init__(self, name='variables'):
        super().__init__(name)
        self.content = ''
        self.vlist = OrderedDict()

    @staticmethod
    def replace_variables(v, content, self_role=None, default_role_map={}):
        """
        Replace all variable and nics references in content
        This is done in two step : variables first, then NICs reference so variable can be used in NIC references
        :param v: Dictionary of variables
        :param content: Text to change
        :param self_role: Role of the caller, that self reference in nic will map to
        :return: The text with reference to variables and nics replaced
        """

        def do_replace(match):
            varname = match.group('varname_sp') if match.group('varname_sp') is not None else match.group('varname_in')
            if (varname in v):
                val = v[varname]
                return str(val[0] if type(val) is tuple else val)
            return match.group(0)

        content = re.sub(
            Variable.VARIABLE_REGEX,
            do_replace, content)

        def do_replace_nics(nic_match):
            varRole = nic_match.group('role')
            return str(npf.node(varRole, self_role, default_role_map).get_nic(
                int(nic_match.group('nic_idx') if nic_match.group('nic_idx') else v[nic_match.group('nic_var')]))[
                           nic_match.group('type')])

        content = re.sub(
            Node.VARIABLE_NICREF_REGEX,
            do_replace_nics, content)

        def do_replace_math(match):
            expr = match.group('expr').strip()
            aeval = Interpreter()
            return str(aeval(expr))

        content = re.sub(
            Variable.MATH_REGEX,
            do_replace_math, content)
        return content

    def replace_all(self, value):
        """Return a list of all possible replacement in values for each combination of variables"""
        values = []
        for v in self:
            values.append(SectionVariable.replace_variables(v, value))
        return values

    def __iter__(self):
        return BruteVariableExpander(self.vlist)

    def __len__(self):
        if len(self.vlist) == 0:
            return 0
        n = 1
        for k, v in self.vlist.items():
            n *= v.count()
        return n

    def dynamics(self):
        """List of non-constants variables"""
        dyn = OrderedDict()
        for k, v in self.vlist.items():
            if v.count() > 1: dyn[k] = v
        return dyn

    def is_numeric(self, k):
        v = self.vlist.get(k, None)
        if v is None:
            return True
        return v.is_numeric()

    def statics(self) -> OrderedDict:
        """List of constants variables"""
        dyn = OrderedDict()
        for k, v in self.vlist.items():
            if v.count() <= 1: dyn[k] = v
        return dyn

    def override_all(self, dict):
        for k, v in dict.items():
            self.override(k, v)

    def override(self, var, val):
        if isinstance(val, Variable):
            self.vlist[var] = val
        else:
            self.vlist[var] = SimpleVariable(var, val)

    def parse_variable(self, line, tags):
        try:
            if not line:
                return None, None, False
            match = re.match(
                r'(?P<tags>' + Variable.TAGS_REGEX + r':)?(?P<name>' + Variable.NAME_REGEX + r')(?P<assignType>=|[+]=)(?P<value>.*)',
                line)
            if not match:
                raise Exception("Invalid variable '%s'" % line)
            var_tags = match.group('tags')[:-1].split(',') if match.group('tags') is not None else []
            for t in var_tags:
                if (t in tags) or (t.startswith('-') and not t[1:] in tags):
                    pass
                else:
                    return None, None, False
            name = match.group('name')
            return name, VariableFactory.build(name, match.group('value'), self), match.group('assignType') == '+='
        except:
            print("Error parsing line %s" % line)
            raise

    def build(self, content, testie):
        for line in content.split("\n"):
            var, val, is_append = self.parse_variable(line, testie.tags)
            if not var is None:
                if is_append:
                    self.vlist[var] += val
                else:
                    self.vlist[var] = val
        return OrderedDict(sorted(self.vlist.items()))

    def finish(self, testie):
        self.vlist = self.build(self.content, testie)

    def dtype(self):
        formats = []
        names = []
        for k, v in self.vlist.items():
            f = v.format()
            formats.append(f)
            names.append(k)
        return dict(names=names, formats=formats)


class SectionLateVariable(SectionVariable):
    def __init__(self, name='late_variables'):
        super().__init__(name)

    def finish(self, testie):
        pass

    def execute(self, variables, testie):

        self.vlist = OrderedDict()
        for k,v in variables.items():
            self.vlist[k] = SimpleVariable(k,v)
        content = self.content

        vlist = self.build(content, testie)
        final = OrderedDict()
        for k,v in vlist.items():
            final[k] = v.makeValues()[0]

        return final


class SectionConfig(SectionVariable):
    def __add(self, var, val):
        self.vlist[var] = SimpleVariable(var, val)

    def __add_list(self, var, list):
        self.vlist[var] = ListVariable(var, list)

    def __add_dict(self, var, dict):
        self.vlist[var] = DictVariable(var, dict)

    def __init__(self):
        super().__init__('config')
        self.content = ''
        self.vlist = {}
        self.__add("accept_outliers_mult", 1)
        self.__add("accept_variance", 1)
        self.__add("timeout", 30)
        self.__add("acceptable", 0.01)
        self.__add("n_runs", 3)
        self.__add("n_retry", 0)
        self.__add_dict("accept_zero", {})
        self.__add("n_supplementary_runs", 3)
        self.__add_dict("var_names", {})
        self.__add_dict("var_unit", {"result": "BPS"})
        self.__add_list("results_expect", [])
        self.__add("legend_loc", "best")
        self.__add("var_hide", {})
        self.__add("var_log", [])
        self.__add("autokill", True)
        self.__add_dict("default_role_map",{})
        self.__add_list("result_regex", [
            r"RESULT(:?-(?P<type>[A-Z0-9_]+))?[ \t]+(?P<value>[0-9.]+)[ ]*(?P<multiplier>[nµgmk]?)(?P<unit>s|b|byte|bits)?"])
        self.__add_list("require_tags", [])

    def var_name(self, key):
        if key in self["var_names"]:
            return self["var_names"][key]
        else:
            return key

    def get_list(self, key):
        var = self.vlist[key]
        v = var.makeValues()
        return v

    def get_dict(self, key):
        var = self.vlist[key]
        try:
            v = var.vdict
        except AttributeError:
            print("WARNING : Error in configuration of %s" % key)
            return {key: var.makeValues()[0]}
        return v

    def get_dict_value(self, var, key, result_type=None, default=None):
        if var in self:
            d = self.get_dict(var)
            if result_type is None:
                return d.get(key, default)
            else:
                if key + "-" + result_type in d:
                    return d.get(key + "-" + result_type)
                else:
                    return d.get(key, default)
        return default

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

    def finish(self, testie):
        super().finish(testie)
        # for k,v in self.vlist.items():
        #     print("config %s is %s" %(k,v.makeValues()))
        #     print("config %s is %s" % (k, self.get_list(k)))
