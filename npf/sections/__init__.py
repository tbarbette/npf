from collections import OrderedDict
import re
import time
from typing import List, Set
from npf.expdesign.fullexp import FullVariableExpander
from npf.expdesign.lhsexp import LHSVariableExpander
from npf.expdesign.randomexp import RandomVariableExpander
from npf.expdesign.zltexp import ZLTVariableExpander
from npf.repository import Repository
from npf.variable import CoVariable, DictVariable, ListVariable, SimpleVariable, Variable, VariableFactory, get_bool, is_bool, replace_variables


class Section:
    def __init__(self, name):
        self.name = name
        self.content = ''
        self.noparse = False

    def get_content(self):
        return self.content

    def finish(self, test):
        pass
    

class SectionNull(Section):
    def __init__(self, name='null'):
        super().__init__(name)
        
class SectionSendFile(Section):
    def __init__(self, role, path):
        super().__init__('sendfile')
        self._role = role
        self.path = path

    def finish(self, test):
        test.sendfile.setdefault(self._role,[]).append(self.path)

    def set_role(self, role):
        self._role = role

class SectionScript(Section):
    TYPE_INIT = "init"
    TYPE_SCRIPT = "script"
    TYPE_EXIT = "exit"
    ALL_TYPES_SET = {TYPE_INIT, TYPE_SCRIPT, TYPE_EXIT}

    num = 0

    def __init__(self, role=None, params=None, jinja=False):
        super().__init__('script')
        if params is None:
            params = {}
        self.params = params
        self._role = role
        self.type = self.TYPE_SCRIPT
        self.index = ++self.num
        self.multi = None
        self.jinja = jinja

    def get_role(self):
        return self._role

    def set_role(self, role):
        self._role = role

    def get_name(self, full=False):
        if 'name' in self.params:
            return self.params['name']
        elif full:
            if self.get_role():
                return "%s [%s]" % (self.get_role(), str(self.index))
            else:
                return "[%s]" % (str(self.index))
        else:
            return str(self.index)

    def get_type(self):
        return self.type

    def finish(self, test):
        test.scripts.append(self)

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

class SectionPyExit(Section):
    num = 0

    def __init__(self, name = ""):
        super().__init__('pyexit')
        self.index = ++self.num
        self.name = name

    def finish(self, test):
        test.pyexits.append(self)

    def get_name(self, full=False):
        if self.name != "":
            return "pyexit_"+str(self.index)
        else:
            return "pyexit_"+self.name



class SectionImport(Section):
    def __init__(self, role=None, module=None, params=None, is_include=False):
        super().__init__('import')
        if params is None:
            params = {}
        self.params = params
        self.is_include = is_include
        self.multi = None
        if is_include:
            self.module = module
        elif module is not None and module != '':
            self.module = 'modules/' + module
        else:
            if not 'test' in params:
                raise Exception("%import section must define a module name or a test=[path] to import")
            self.module = params['test']
            del params['test']

        self._role = role

    def get_role(self):
        return self._role

    def finish(self, test):
        content = self.get_content().strip()
        if content != '':
            raise Exception("%%import section does not support any content (got %s)" % content)
        test.imports.append(self)


class SectionFile(Section):
    def __init__(self, filename, role=None, noparse=False, jinja=False):
        super().__init__('file')
        self.content = ''
        self.filename = filename
        self._role = role
        self.noparse = noparse
        self.jinja = jinja

    def get_role(self):
        return self._role

    def finish(self, test):
        test.files.append(self)


class SectionInitFile(SectionFile):
    def __init__(self, filename, role=None, noparse=False):
        super().__init__(filename, role, noparse)

    def finish(self, test):
        test.init_files.append(self)


class SectionRequire(Section):
    def __init__(self, jinja=False):
        super().__init__('require')
        self.content = ''
        self.jinja = jinja

    def role(self):
        # For now, require is only on one node, the default one
        return 'default'

    def finish(self, test):
        test.requirements.append(self)

class SectionVariable(Section):
    def __init__(self, name='variables'):
        super().__init__(name)
        self.content = ''
        self.vlist = OrderedDict()
        self.aliases = {}

    @staticmethod
    def replace_variables(v: dict, content: str, self_role=None,self_node=None, default_role_map={}):
        return replace_variables(v, content, self_role, self_node, default_role_map)

    def replace_all(self, value):
        """Return a list of all possible replacement in values for each combination of variables"""
        values = []
        for v in self:
            values.append(SectionVariable.replace_variables(v, value))
        return values

    def expand(self, results=None, method="full", overriden=set()):
        """Expands variables based on the specified method.

        This method determines how to expand the variables in the list based on the provided method.
        It can return different types of variable expanders depending on the method specified, including
        random shuffling or specific ZLT expansions.

        Args:
            results (dict, optional): A dictionary of previous results for iterative methods. Defaults to an empty dictionary.
            method (str, optional): The method to use for expansion. Can be "full", "shuffle", "rand", "random", or variations of "zl". Defaults to "full".
            overriden (set, optional): A set of overridden variables. Defaults to an empty set.

        Returns:
            VariableExpander: An instance of the appropriate variable expander based on the method specified.

        """

        if results is None:
            results = {}
        a = method.find("(")
        params = []

        if a > 0:
            params = method[a + 1:-1].split(",")
        if method == "shuffle" or method.startswith("rand"):
            if len(params) >= 1:
                seed = int(params[0])
            else:
                print("WARNING: Using a time-based seed. Please set the seed with --exp-design random(42)")
                seed = time.time()
            return RandomVariableExpander(self.vlist, overriden, seed = seed, n_iter = int(params[1]) if len(params) >= 2 else -1)
        elif method.startswith("lhs"):
            if len(params) >= 1:
                seed = int(params[0])
            else:
                print("WARNING: Using a time-based seed. Please set the seed with --exp-design lhs(42)")
                seed = time.time()
            return LHSVariableExpander(self.vlist, overriden, seed = seed, n_iter = int(params[1]) if len(params) >= 2 else -1)
        elif "zl" in method.lower():
            if method.lower().startswith("allzl"):
                all_lower = True
                perc = method.lower()[5] == 'p'
            else:
                all_lower = False
                perc = method.lower()[2] == 'p'
            return ZLTVariableExpander(self.vlist, overriden=overriden, results=results, input=params[0], output=params[1], margin=1.01 if len(params) == 2 else float(params[2]), all=all_lower, perc=perc)

        else:
            return FullVariableExpander(self.vlist, overriden)

    def __iter__(self):
        return self.expand()

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

    @staticmethod
    def _assign(vlist, assign, var, val):
                    cov = None
                    for k,v in vlist.items():
                        if isinstance(v,CoVariable):
                            if var in v.vlist:
                                cov = v.vlist
                                break

                    if assign == '+=':
                        #If in covariable, remove that one
                        if cov:
                            print("NOTE: %s is overwriting a covariable, the covariable will be ignored" % var)
                            del cov[var]
                        if var in vlist:
                            vlist[var] += val
                        else:
                            vlist[var] = val
                    elif assign == '?=':
                        #If in covariable or already in vlist, do nothing
                        if not cov and not var in vlist:
                            vlist[var] = val
                    else:
                        #If in covariable, remove it as we overwrite the value
                        if cov:
                            del cov[var]
                        vlist[var] = val
    def override(self, var, val):
        found = False
        for k,v in self.vlist.items():
            if isinstance(v, CoVariable):
                if var in v.vlist:
                    found = True
                    break
            if k == var:
                found = True
                break
        if not found:
            print("WARNING : %s does not override anything" % var)

        if not isinstance(val, Variable):
            val = SimpleVariable(var, val)
        else:
            if val.is_default:
                return

        self._assign(self.vlist, val.assign, var, val)

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
    def parse_variable(line, tags, vsection=None, fail=True):
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
            if fail:
                print("Error parsing line %s" % line)
                raise
            else:
                return None, None, False

    def build(self, content:str, test, check_exists:bool=False, fail:bool=True):
        sections_stack = [self]
        for line in content.split("\n"):
            if line.strip() == "{":
                c = CoVariable()
                sections_stack.append(c)
                self.vlist[c.name] = c
            elif line.strip() == "}":
                sections_stack.pop()
                for k in c.vlist.keys():
                    if k in self.vlist:
                        del self.vlist[k]
            else:
                line = line.lstrip()
                sect = sections_stack[-1]
                var, val, assign = self.parse_variable(line, test.tags, vsection=sect, fail=fail)
                if not var is None and not val is None:
                    # If check_exists, we verify that we overwrite a variable. This is used by config section to ensure we write known parameters
                    if check_exists and not var in sect.vlist:
                        if var.endswith('s') and var[:-1] in sect.vlist:
                            var = var[:-1]
                        elif var + 's' in sect.vlist:
                            var = var + 's'
                        else:
                            if var in self.aliases:
                                var = self.aliases[var]
                            else:
                                raise Exception("Unknown variable %s" % var)
                    self._assign(sect.vlist, assign, var, val)
        return OrderedDict(self.vlist.items())

    def finish(self, test):
        self.vlist = self.build(self.content, test)

    def dtype(self):
        formats = []
        names = []
        for k, v in self.vlist.items():
            k, f = v.format()
            if type(f) is list:
                formats.extend(f)
                names.extend(k)
            else:
                formats.append(f)
                names.append(k)
        return OrderedDict(names=names, formats=formats)


class SectionLateVariable(SectionVariable):
    def __init__(self, name='late_variables'):
        super().__init__(name)

    def finish(self, test):
        test.late_variables.append(self)

    def execute(self, variables, test, fail=True):
        self.vlist = OrderedDict()
        for k, v in variables.items():
            self.vlist[k] = SimpleVariable(k, v)
        content = self.content

        vlist = self.build(content, test, fail=fail)
        final = OrderedDict()
        for k, v in vlist.items():
            vals = v.makeValues()
            if len(vals) > 0:
                final[k] = vals[0]

        return final


class SectionConfig(SectionVariable):
    def __add(self, var, val):
        v = SimpleVariable(var, val)
        v.is_default = True
        self.vlist[var.lower()] = v

    def __add_list(self, var, list):
        v = ListVariable(var, list)
        v.is_default = True
        self.vlist[var.lower()] = v

    def __add_dict(self, var, dict):
        v = DictVariable(var, dict)
        v.is_default = True
        self.vlist[var.lower()] = v

    def __init__(self):
        super().__init__('config')
        self.content = ''
        self.vlist = {}

        self.aliases = {
            'graph_variable_as_series': 'graph_variables_as_series',
            'graph_variable_as_serie': 'graph_variables_as_series',
            'graph_variables_as_serie': 'graph_variables_as_series',
            'graph_subplot_variables' : 'graph_subplot_variable',
            'graph_grid': 'var_grid',
            'graph_ticks' : 'var_ticks',
            'graph_serie': 'var_serie',
            'graph_types':'graph_type',
            'graph_linestyle': 'graph_lines',
            'var_combine': 'graph_combine_variables',
            'series_as_variables': 'graph_series_as_variables',
            'var_as_series': 'graph_variables_as_series',
            'result_as_variables': 'graph_result_as_variables',
            'y_group': 'graph_y_group',
            'graph_serie_sort':'graph_series_sort',
            'series_prop': 'graph_series_prop',
            'graph_legend_ncol': 'legend_ncol',
            'graph_legend_loc': 'legend_loc',
            'graph_do_legend' : 'graph_legend',
            'do_legend'     : 'graph_legend',
            'var_label_dir' : 'graph_label_dir',
            'graph_max_col' : 'graph_max_col',

        }

        # Environment
        self.__add("default_repo", "local")

        # Regression related
        self.__add_list("accept_zero", ["time", "DROP", "DROPPED", "DROPPEDPC", "LOST"])
        self.__add("n_supplementary_runs", 3)
        self.__add("acceptable", 0.01)
        self.__add("accept_outliers_mult", 1)
        self.__add("accept_variance", 1)

        # Test related

        self.__add_list("time_kinds", [])
        self.__add("n_runs", 3)
        self.__add("n_retry", 0)
        self.__add_dict("var_n_runs", {})
        self.__add_dict("var_markers", {}) #Do not set CDF here, small CDF may want them, and then scatterplot would not work
        self.__add("result_add", False)
        self.__add("result_append", False)
        self.__add("result_overwrite", False)
        self.__add_list("result_regex", [
            r"(:?(:?(?P<kind>[A-Z0-9_]+)-)?(?P<time_value>[0-9.]+)-)?RESULT(:?-(?P<type>[A-Z0-9_:~.@()-]+))?[ \t]+(?P<value>[0-9.]+(e[+-][0-9]+)?)[ ]*(?P<multiplier>[nµugmkKGT]?)(?P<unit>s|sec|b|byte|bits)?"])
        self.__add_list("results_expect", [])
        self.__add("autokill", True)
        self.__add("critical", False)
        self.__add_dict("env", {})  # Unimplemented yet
        self.__add("timeout", 30)
        self.__add("hardkill", 5000)

        # Role related
        self.__add_dict("default_role_map", {})
        self.__add_list("role_exclude", [])

        # Graph options
        self.__add_dict("graph_combine_variables", {})
        self.__add_dict("graph_subplot_results", {})
        self.__add("graph_subplot_variable", None)
        self.__add("graph_subplot_unique_legend", False)
        self.__add_list("graph_display_statics", [])
        self.__add_list("graph_variables_as_series", [])
        self.__add("graph_variables_explicit", False)
        self.__add_list("graph_hide_variables", [])
        self.__add_dict('graph_result_as_variable', {})
        self.__add_dict('graph_map', {})
        self.__add_dict('graph_x_sort', {})
        self.__add("graph_scatter", False)
        self.__add("graph_show_values", False)
        self.__add("graph_show_ylabel", True)
        self.__add("graph_show_xlabel", True)
        self.__add("graph_subplot_type", "subplot")
        self.__add("graph_max_series", None)
        self.__add("graph_max_cols", 2)
        self.__add("graph_series_as_variables", False)
        self.__add("graph_series_prop", False)
        self.__add("graph_series_sort", None)
        self.__add("graph_series_label", None)
        self.__add_dict("graph_filter_by", {})
        self.__add("graph_filter_linestyle", "--")
        self.__add("graph_filter_fillstyle", "none")
        self.__add("graph_bar_stack", False)
        self.__add("graph_text",'')
        self.__add("graph_legend", None), #the default behavior depends upon the type of graph
        self.__add("graph_error_fill",False)
        self.__add_dict("graph_error", {"CDF":"none"})
        self.__add("graph_mode",None)
        self.__add_dict("graph_y_group",{})
        self.__add_list("graph_color", [])
        self.__add_list("graph_markers", ['o', '^', 's', 'D', '*', 'x', '.', '_', 'H', '>', '<', 'v', 'd'])
        self.__add_list("graph_lines", ['-', '--', '-.', ':'])
        self.__add_list("legend_bbox", [0, 1, 1, .05])
        self.__add("legend_loc", "best")

        self.__add("legend_frameon", True)
        self.__add("legend_ncol", 1)
        self.__add("var_hide", {})
        self.__add_list("var_log", [])
        self.__add_dict("var_log_base", {})
        self.__add_dict("var_divider", {'result': 1})
        self.__add_dict("var_lim", {})
        self.__add_dict("var_format", {})
        self.__add_dict("var_ticks", {})

        self.__add_dict("graph_legend_params", {})
        self.__add_list("var_grid", ["result"])
        self.__add("graph_grid_linestyle", ":")

        self.__add("graph_fillstyle", "full")
        self.__add_dict("graph_tick_params", {})
        self.__add("var_serie",None)
        self.__add_dict("var_names", {"result-LATENCY":"Latency (µs)", "result-THROUGHPUT":"Throughput", "^THROUGHPUT$":"Throughput", "boxplot":"", "^PARALLEL$":"Number of parallel connections", "^ZEROCOPY$":"Zero-Copy", "CDFLATPC":"CDF", "CDFLATVAL":"Latency"})
        self.__add_dict("var_unit", {"result": "","result-LATENCY":"us","latency":"us","throughput":"bps"})
        self.__add("graph_show_fliers", True)
        self.__add_dict("graph_cross_reference", {})
        self.__add_dict("graph_background", {})
        self.__add_dict("var_round", {})
        self.__add_dict("var_aggregate", {})
        self.__add_dict("var_drawstyle", {})
        self.__add_list("graph_type", [])
        self.__add("title", None)
        self.__add_list("require_tags", [])
        self.__add_dict("graph_label_dir", {})
        self.__add("graph_force_diagonal_labels", False)
        self.__add("graph_smooth", 1)

        # Time series
        self.__add("time_precision", 1)
        self.__add("time_sync", False)
        self.__add_list("glob_sync", [])
        self.__add_list("var_sync", ["time"])
        self.__add_dict("var_shift", {})
        self.__add_dict("var_repeat", {})

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
        best_l = -1
        best = default
        if var in self:
            if not isinstance(self.vlist[var], DictVariable) and self.vlist[var]:
                return self[var]

            d = self.get_dict(var)
            if result_type is not None:
                #Search for "key-result_type", such as result-throughput
                kr = key + "-" + result_type
                for k, v in d.items():
                    m = re.search(k,kr,re.IGNORECASE)
                    if m:
                        l =  len(m.group(0))
                        if (best_l < l):
                            best_l = l
                            best = v

                #Search for result type alone such as throughput
                for k, v in d.items():
                    m = re.search(k, result_type,re.IGNORECASE)
                    if m:
                        l =  len(m.group(0))
                        if (best_l < l):
                            best_l = l
                            best = v

                if var in d:
                    return d[var]

            #Search for the exact key if there is no result_type
            for k, v in d.items():
                m = re.search(k, key, re.IGNORECASE)
                if m:
                    l =  len(m.group(0))
                    if (best_l < l):
                        best_l = l
                        best = v

        return best

    def get_bool(self, key):
        return get_bool(self[key])

    def get_bool_or_in(self, var, obj, default=None):
        val = self[var]

        if type(val) == type(obj) and val == obj:
            return True

        if isinstance(val, list):
            return obj in val
        if is_bool(val):
            return get_bool(val)
        return default

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
        try:
            for match in self.get_list(key):
                if re.match(match, val):
                    return True
        except Exception:
            print("ERROR : Regex %s does not work" % key)
        return False

    def finish(self, test):
        self.vlist = self.build(self.content, test, check_exists=True)

