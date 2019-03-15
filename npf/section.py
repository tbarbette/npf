import ast

from typing import List, Set

from npf import npf
from npf.repository import Repository
from .variable import *
from collections import OrderedDict

from random import shuffle

import re


class SectionFactory:
    varPattern = "([a-zA-Z0-9_:-]+)[=](" + Variable.VALUE_REGEX + ")?"
    namePattern = re.compile(
        "^(?P<tags>" + Variable.TAGS_REGEX + "[:])?(?P<name>info|config|variables|exit|pypost|pyexit|late_variables|include (?P<includeName>[a-zA-Z0-9_./-]+)||(init-)?file(:?[@](?P<fileRole>[a-zA-Z0-9]+))? (?P<fileName>[a-zA-Z0-9_.-]+)(:? (?P<fileNoparse>noparse))?|require|"
                                             "import(:?[@](?P<importRole>[a-zA-Z0-9]+))?[ \t]+(?P<importModule>" + Variable.VALUE_REGEX + ")(?P<importParams>([ \t]+" +
        varPattern + ")+)?|" +
                     "sendfile(:?[@](?P<sendfileRole>[a-zA-Z0-9]+))?[ \t]+(?P<sendfilePath>.*)|" +
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

        if not SectionVariable.match_tags(matcher.group('tags'), testie.tags):
            return SectionNull()
        sectionName = matcher.group('name')

        s = None

        if sectionName.startswith('import'):
            params = matcher.group('importParams')
            module = matcher.group('importModule')
            params = dict(re.findall(SectionFactory.varPattern, params)) if params else {}
            s = SectionImport(matcher.group('importRole'), module, params)
            return s

        if sectionName.startswith('sendfile'):
            s = SectionSendFile(matcher.group('sendfileRole'), matcher.group('sendfilePath'))
            return s

        if sectionName.startswith('script') or (
                sectionName.startswith('init') and not sectionName.startswith('init-file')):
            params = matcher.group('scriptParams')
            params = dict(re.findall(SectionFactory.varPattern, params)) if params else {}
            s = SectionScript(matcher.group('scriptRole'), params)
            if sectionName.startswith('init'):
                s.init = True
                s.params.setdefault("autokill", False)
            return s

        if matcher.group('scriptParams') is not None:
            raise Exception("Only script sections takes arguments (" + sectionName + " has argument " +
                            matcher.groups("params") + ")")

        if sectionName.startswith('file'):
            s = SectionFile(matcher.group('fileName').strip(), role=matcher.group('fileRole'),
                            noparse=matcher.group('fileNoparse'))
            return s
        if sectionName.startswith('init-file'):
            s = SectionInitFile(matcher.group('fileName').strip(), role=matcher.group('fileRole'),
                                noparse=matcher.group('fileNoparse'))
            return s
        elif sectionName.startswith('include'):
            s = SectionImport(None, matcher.group('includeName').strip(), {}, is_include=True)
            return s
        elif sectionName == 'require':
            s = SectionRequire()
            return s
        elif sectionName == 'late_variables':
            s = SectionLateVariable()
            return s
        if hasattr(testie, sectionName):
            raise Exception("Only one section of type " + sectionName + " is allowed")

        if sectionName == 'variables':
            s = SectionVariable()
        elif sectionName == 'pyexit':
            s = Section('pyexit')
        elif sectionName == 'pypost':
            s = Section('pypost')
        elif sectionName == 'exit':
            s = Section('exit')
        elif sectionName == 'config':
            s = SectionConfig()
        elif sectionName == 'info':
            s = Section('info')
        if s is None:
            raise Exception("Unknown section %s" % sectionName)
        setattr(testie, s.name, s)
        return s


class Section:
    def __init__(self, name):
        self.name = name
        self.content = ''
        self.noparse = False

    def get_content(self):
        return self.content

    def finish(self, testie):
        pass


class SectionNull(Section):
    def __init__(self, name='null'):
        super().__init__(name)

class SectionSendFile(Section):
    def __init__(self, role, path):
        super().__init__('sendfile')
        self._role = role
        self.path = path

    def finish(self, testie):
        testie.sendfile.setdefault(self._role,[]).append(self.path)

    def set_role(self, role):
        self._role = role

class SectionScript(Section):
    TYPE_INIT = "init"
    TYPE_SCRIPT = "script"
    ALL_TYPES_SET = {TYPE_INIT, TYPE_SCRIPT}

    num = 0

    def __init__(self, role=None, params=None):
        super().__init__('script')
        if params is None:
            params = {}
        self.params = params
        self._role = role
        self.init = False
        self.index = ++self.num

    def get_role(self):
        return self._role

    def set_role(self, role):
        self._role = role

    def get_name(self, full=False):
        if 'name' in self.params:
            return self.params['name']
        elif full:
            return "%s [%s]" % (self.get_role(), str(self.index))
        else:
            return str(self.index)

    def get_type(self):
        return SectionScript.TYPE_INIT if self.init else SectionScript.TYPE_SCRIPT

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
    def __init__(self, role=None, module=None, params=None, is_include=False):
        super().__init__('import')
        if params is None:
            params = {}
        self.params = params
        self.is_include = is_include
        if is_include:
            self.module = module
        elif module is not None and module is not '':
            self.module = 'modules/' + module
        else:
            if not 'testie' in params:
                raise Exception("%import section must define a module name or a testie=[path] to import")
            self.module = params['testie']
            del params['testie']

        self._role = role

    def get_role(self):
        return self._role

    def finish(self, testie):
        content = self.get_content().strip()
        if content != '':
            raise Exception("%%import section does not support any content (got %s)" % content)
        testie.imports.append(self)


class SectionFile(Section):
    def __init__(self, filename, role=None, noparse=False):
        super().__init__('file')
        self.content = ''
        self.filename = filename
        self._role = role
        self.noparse = noparse

    def get_role(self):
        return self._role

    def finish(self, testie):
        testie.files.append(self)


class SectionInitFile(SectionFile):
    def __init__(self, filename, role=None, noparse=False):
        super().__init__(filename, role, noparse)

    def finish(self, testie):
        testie.init_files.append(self)


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

    def __iter__(self):
        return self.expanded.__iter__()

    def __next__(self):
        return self.it.__next__()


class RandomVariableExpander(BruteVariableExpander):
    """Same as BruteVariableExpander but shuffle the series to test"""

    def __init__(self, vlist):
        super().__init__(vlist)
        shuffle(self.expanded)
        self.it == self.expanded.__iter__()


class SectionVariable(Section):
    def __init__(self, name='variables'):
        super().__init__(name)
        self.content = ''
        self.vlist = OrderedDict()
        self.aliases = {}

    @staticmethod
    def replace_variables(v: dict, content: str, self_role=None, default_role_map={}):
        return replace_variables(v,content,self_role,default_role_map)

    def replace_all(self, value):
        """Return a list of all possible replacement in values for each combination of variables"""
        values = []
        for v in self:
            values.append(SectionVariable.replace_variables(v, value))
        return values

    def expand(self, method=None):
        if method == "shuffle" or method == "rand" or method == "random":
            return RandomVariableExpander(self.vlist)
        else:
            return BruteVariableExpander(self.vlist)

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

    def override_all(self, d):
        for k, v in d.items():
            self.override(k, v)

    def override(self, var, val):
        if not var in self.vlist:
            print("WARNING : %s does not override anything" % var)
        if isinstance(val, Variable):
            if val.assign == '+=':
                self.vlist[var] += val
            elif val.assign == '?=' and not var in self.vlist:
                self.vlist[var] = val
            else:
                self.vlist[var] = val
        else:
            self.vlist[var] = SimpleVariable(var, val)

    @staticmethod
    def match_tags(text, tags):
        if not text or text == ':':
            return True
        if text.endswith(':'):
            text = text[:-1]
        var_tags_ors = text.split('|')
        valid = False
        for var_tags_or in var_tags_ors:
            var_tags = var_tags_or.split(',')
            has_this_or = True
            for t in var_tags:
                if (t in tags) or (t.startswith('-') and not t[1:] in tags):
                    pass
                else:
                    has_this_or = False
                    break
            if has_this_or:
                valid = True
                break
        return valid

    @staticmethod
    def parse_variable(line, tags, vsection=None):
        try:
            if not line:
                return None, None, False
            match = re.match(
                r'(?P<tags>' + Variable.TAGS_REGEX + r':)?(?P<name>' + Variable.NAME_REGEX + r')(?P<assignType>=|[+?]=)(?P<value>.*)',
                line)
            if not match:
                raise Exception("Invalid variable '%s'" % line)
            if not SectionVariable.match_tags(match.group('tags'), tags):
                return None, None, False

            name = match.group('name')
            return name, VariableFactory.build(name, match.group('value'), vsection), match.group('assignType')
        except:
            print("Error parsing line %s" % line)
            raise

    def build(self, content, testie, check_exists=False):
        for line in content.split("\n"):
            var, val, assign = self.parse_variable(line, testie.tags, self)
            if not var is None and not val is None:
                if check_exists and not var in self.vlist:

                    if var.endswith('s') and var[:-1] in self.vlist:
                        var = var[:-1]
                    elif var + 's' in self.vlist:
                        var = var + 's'
                    else:
                        if var in self.aliases:
                            var = self.aliases[var]
                        else:
                            raise Exception("Unknown variable %s" % var)
                if assign == '+=' and var in self.vlist:
                    self.vlist[var] += val
                elif assign == '?=':
                    if not var in self.vlist:
                        self.vlist[var] = val
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
        testie.late_variables.append(self)

    def execute(self, variables, testie):
        self.vlist = OrderedDict()
        for k, v in variables.items():
            self.vlist[k] = SimpleVariable(k, v)
        content = self.content

        vlist = self.build(content, testie)
        final = OrderedDict()
        for k, v in vlist.items():
            vals = v.makeValues()
            if len(vals) > 0:
                final[k] = vals[0]

        return final


class SectionConfig(SectionVariable):
    def __add(self, var, val):
        self.vlist[var.lower()] = SimpleVariable(var, val)

    def __add_list(self, var, list):
        self.vlist[var.lower()] = ListVariable(var, list)

    def __add_dict(self, var, dict):
        self.vlist[var.lower()] = DictVariable(var, dict)

    def __init__(self):
        super().__init__('config')
        self.content = ''
        self.vlist = {}

        self.aliases = {
            'graph_variable_as_series': 'graph_variables_as_series',
            'graph_grid': 'var_grid',
            'graph_serie': 'var_serie',
            'var_combine': 'graph_combine_variables',
            'series_as_variables': 'graph_series_as_variables',
            'var_as_series': 'graph_variables_as_series',
            'result_as_variables': 'graph_result_as_variables',
            'series_prop': 'graph_series_prop',
            'graph_legend_ncol': 'legend_ncol'
        }

        # Environment
        self.__add("default_repo", None)

        # Regression related
        self.__add_list("accept_zero", ["time"])
        self.__add("n_supplementary_runs", 3)
        self.__add("acceptable", 0.01)
        self.__add("accept_outliers_mult", 1)
        self.__add("accept_variance", 1)

        # Test related
        self.__add("n_runs", 3)
        self.__add("n_retry", 0)
        self.__add_dict("var_n_runs", {})
        self.__add_dict("var_markers", {})
        self.__add("result_add", True)
        self.__add_list("result_regex", [
            r"(:?(?P<time>[0-9.]+)-)?RESULT(:?-(?P<type>[A-Z0-9_:~.@()-]+))?[ \t]+(?P<value>[0-9.]+(e[+-][0-9]+)?)[ ]*(?P<multiplier>[nµugmkKGT]?)(?P<unit>s|sec|b|byte|bits)?"])
        self.__add_list("results_expect", [])
        self.__add("autokill", True)
        self.__add("critical", False)
        self.__add_dict("env", {})  # Unimplemented yet
        self.__add("timeout", 30)
        self.__add("time_precision", 1)
        self.__add("time_sync", True)

        # Role related
        self.__add_dict("default_role_map", {})
        self.__add_list("role_exclude", [])

        # Graph options
        self.__add_dict("graph_combine_variables", {})
        self.__add_dict("graph_subplot_results", {})
        self.__add("graph_subplot_variable", None)
        self.__add_list("graph_display_statics", [])
        self.__add_list("graph_variables_as_series", [])
        self.__add_list("graph_hide_variables", [])
        self.__add_dict('graph_result_as_variable', {})
        self.__add_dict('graph_map', {})
        self.__add_dict('graph_x_sort', {})
        self.__add("graph_scatter", False)
        self.__add("graph_show_values", False)
        self.__add("graph_subplot_type", "subplot")
        self.__add("graph_max_series", None)
        self.__add("graph_series_as_variables", False)
        self.__add("graph_series_prop", False)
        self.__add("graph_series_sort", None)
        self.__add("graph_series_label", None)
        self.__add("graph_bar_stack", False)
        self.__add("graph_text",'')
        self.__add("graph_legend",True)
        self.__add("graph_error_fill",False)
        self.__add_dict("graph_error", {})
        self.__add("graph_mode",None)
        self.__add_dict("graph_y_group",{})
        self.__add_list("graph_color", [])
        self.__add_list("graph_markers", ['o', '^', 's', 'D', '*', 'x', '.', '_', 'H', '>', '<', 'v', 'd'])
        self.__add_list("graph_lines", ['-', '--', '-.', ':'])
        self.__add_list("legend_bbox", [0, 1, 1, .1])
        self.__add("legend_loc", "best")
        self.__add("legend_ncol", 1)
        self.__add("var_hide", {})
        self.__add_list("var_log", [])
        self.__add_dict("var_log_base", {})
        self.__add_dict("var_divider", {'result': 1})
        self.__add_dict("var_lim", {})
        self.__add_dict("var_format", {})
        self.__add_dict("var_ticks", {})
        self.__add_list("var_grid", [])
        self.__add_list("test_time_sync", [])
        self.__add("var_serie",None)
        self.__add_dict("var_names", {"result-LATENCY":"Latency (µs)","result-THROUGHPUT":"Throughput","boxplot":""})
        self.__add_dict("var_unit", {"result": "bps","result-LATENCY":"us","latency":"us","throughput":"bps"})
        self.__add_dict("var_round", {})
        self.__add_dict("var_aggregate", {})
        self.__add_dict("var_repeat", {})
        self.__add_dict("var_drawstyle", {})
        self.__add_list("graph_type", [])
        self.__add("title", None)
        self.__add_list("require_tags", [])

    def var_name(self, key):
        key = key.lower()
        if key in self["var_names"]:
            return self["var_names"][key]
        else:
            return key

    def get_list(self, key):
        key = key.lower()
        var = self.vlist[key]
        v = var.makeValues()
        return v

    def get_dict(self, key):
        key = key.lower()
        var = self.vlist[key]
        try:
            v = OrderedDict()
            for k,l in var.vdict.items():
                v[k.strip()] = l
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
                elif result_type in d:
                    return d.get(result_type)
                else:
                    return d.get(key, default)
        if key != key.lower():
            return self.get_dict_value(var, key.lower(), result_type, default)
        return default

    def get_bool(self, key):
        return get_bool(self[key])

    def __contains__(self, key):
        return key.lower() in self.vlist

    def __getitem__(self, key):
        var = self.vlist[key.lower()]
        v = var.makeValues()
        if type(v) is list and len(v) == 1:
            return v[0]
        else:
            return v

    def __setitem__(self, key, val):
        self.__add(key.lower(), val)

    def match(self, key, val):
        for match in self.get_list(key):
            if re.match(match, val):
                return True
        return False

    def finish(self, testie):
        self.vlist = self.build(self.content, testie, check_exists=True)
