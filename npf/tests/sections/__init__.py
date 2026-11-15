from collections import OrderedDict
import re
import time
from typing import List, Set
from npf.expdesign.fullexp import FullVariableExpander
from npf.expdesign.gpexp import GPVariableExpander
from npf.expdesign.lhsexp import LHSVariableExpander
from npf.expdesign.multiexp import MultiVariableExpander
from npf.expdesign.randomexp import RandomVariableExpander
from npf.expdesign.twokexp import TWOKVariableExpander
from npf.expdesign.zltexp import ZLTVariableExpander, MinAcceptableVariableExpander
from npf.models.units import is_bool
from npf.models.variables.variable import Variable
from npf.models.variables.CoVariable import CoVariable
from npf.models.variables.DictVariable import DictVariable
from npf.models.variables.ListVariable import ListVariable
from npf.models.variables.SimpleVariable import SimpleVariable
from npf.models.variables.VariableFactory import VariableFactory
from npf.repo.repository import Repository
from npf.tests.variable import get_bool, replace_variables


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
    """
    A %script, %init, %exit or %cleanup section: %script[@ROLE[-N]] [jinja] [python-inline] [PARAM=VALUE ...]

    Its parameters, documented in tests.rst of npf-docs:
      name=NAME       Name of the script in NPF's messages and in the output files of --preserve-temporaries
      sudo=true       Run the script with sudo
      delay=SECONDS   Start the script this many seconds after the run starts, or after its waitfor event
      waitfor=EVENT   Start the script when another script prints "EVENT EVENT"
      deps=A,B        Repositories the script needs: NPF builds them, and adds their binaries to the PATH
      timeout=S       Seconds after which the script is stopped (default: timeout of %config)
      autokill=false  When this script ends, do not stop the other scripts (default: autokill of %config)
      nokill=true     At the end of the run, let this script end by itself (default: nokill of %config)
      hardkill=MS     Milliseconds the script has to exit once stopped (default: hardkill of %config)
      critical=true   When this script fails, stop the test (default: critical of %config)
    %import takes delay, waitfor, autokill and nokill for all the scripts of the module, and as_init, which has
    no effect. Its other parameters set variables of the module.
    """
    TYPE_INIT = "init"
    TYPE_SCRIPT = "script"
    TYPE_EXIT = "exit"
    TYPE_CLEANUP = "cleanup"
    ALL_TYPES_SET = {TYPE_INIT, TYPE_SCRIPT, TYPE_EXIT, TYPE_CLEANUP}

    num = 0

    def __init__(self, role=None, params=None, jinja=False, python_inline=False):
        super().__init__('script')
        if params is None:
            params = {}
        self.params = params
        self._role = role
        self.type = self.TYPE_SCRIPT
        self.index = ++self.num
        self.multi = None
        self.jinja = jinja
        self.python_inline = python_inline

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
    def __init__(self, filename, role=None, noparse=False, jinja=False, python_inline=False):
        super().__init__('file')
        self.content = ''
        self.filename = filename
        self._role = role
        self.noparse = noparse
        self.jinja = jinja
        self.python_inline = python_inline

    def get_role(self):
        return self._role

    def finish(self, test):
        test.files.append(self)


class SectionInitFile(SectionFile):
    def __init__(self, filename, role=None, noparse=False,jinja=False, python_inline=False):
        super().__init__(filename, role, noparse)
        self.jinja = jinja
        self.python_inline = python_inline

    def finish(self, test):
        test.init_files.append(self)


class SectionRequire(Section):
    def __init__(self, jinja=False,python_inline=False):
        super().__init__('require')
        self.content = ''
        self.jinja = jinja
        self.python_inline = python_inline

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

    def _expand_single(self, results, m, overriden):
            a = m.find("(")
            params = []

            if a > 0:
                params = m[a + 1:-1].split(",")
            if m.lower() == "shuffle" or m.lower().startswith("rand"):
                if len(params) >= 1:
                    seed = int(params[0])
                else:
                    print("WARNING: Using a time-based seed. Please set the seed with --exp-design random(42)")
                    seed = int(time.time())
                return RandomVariableExpander(self.vlist, overriden, seed = seed, n_iter = int(params[1]) if len(params) >= 2 else -1)
            elif m.lower().startswith("gp"):
                if len(params) >= 1:
                    seed = int(params[0])
                else:
                    print("WARNING: Using a time-based seed. Please set the seed with --exp-design gp(42)")
                    seed = int(time.time())
                return GPVariableExpander(self.vlist, results=results, overriden=overriden, seed = seed, ci = float(params[1]) if len(params) >= 2 else 0.95, outputs=params[2:] if len(params) >= 3 else [])
            elif m.lower().startswith("lhs") or m.lower().startswith("maximin"):
                if len(params) >= 1:
                    seed = int(params[0])
                else:
                    print("WARNING: Using a time-based seed. Please set the seed with --exp-design lhs(42)")
                    seed = int(time.time())
                return LHSVariableExpander(self.vlist, overriden, seed = seed, n_iter = int(params[1]) if len(params) >= 2 else -1)
            elif "zl" in m.lower():
                if m.lower().startswith("nearzl"):
                    all_lower = 2
                    perc = m.lower()[7] == 'p'
                elif m.lower().startswith("allzl"):
                    all_lower = 1
                    perc = m.lower()[6] == 'p'
                else:
                    all_lower = 0
                    perc = m.lower()[3] == 'p'
                monotonic = m.lower()[-1] == 'm'
                return ZLTVariableExpander(self.vlist, overriden=overriden, results=results, input=params[0], output=params[1],
                                           margin=1.01 if len(params) == 2 else float(params[2]), all=all_lower, perc=perc, monotonic=monotonic,
                                           constraints=params[3:] if len(params) > 3 else [])
            elif "minacceptable" in m.lower():
                return MinAcceptableVariableExpander(self.vlist, overriden=overriden, results=results, input=params[0], output=params[1], margin=1.01 if len(params) == 2 else float(params[2]))
            elif m.lower()=="2k":
                return TWOKVariableExpander(self.vlist, overriden=overriden)
            else:
                return FullVariableExpander(self.vlist, overriden)

    def expand(self, results=None, method="full", overriden=set()):
        """Expands variables based on the specified method.

        This method determines how to expand the variables in the list based on the provided method.
        It can return different types of variable expanders depending on the method specified, including
        random shuffling, 2K or specific zero-loss-throughput expansions.

        Multiple methods can be given in which case methods will run one after the other. This allows bootstrapping.

        Args:
            results (dict, optional): A dictionary of previous results for iterative methods. Defaults to an empty dictionary.
            method (str, optional): The method to use for expansion. Can be "full", "shuffle", "2k", "rand", "random", or variations of "zl". Defaults to "full".
            overriden (set, optional): A set of overridden variables. Defaults to an empty set.

        Returns:
            VariableExpander: An instance of the appropriate variable expander based on the method specified.

        """
        if results is None:
            results = {}

        methods = re.split("[;\n]", method)
        if len(methods) == 1:
            return self._expand_single(results, method, overriden)
        else:
            return MultiVariableExpander([self._expand_single(results, m, overriden) for m in methods])



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
            if isinstance(val, (list, tuple)):
                val = ListVariable(var, list(val))
            elif isinstance(val, dict):
                val = DictVariable(var, val)
            else:
                val = SimpleVariable(var, val)
        else:
            if val.is_default:
                return

        self._assign(self.vlist, getattr(val, "assign", "="), var, val)

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
    def parse_variable(line, tags, vsection=None, fail=True, base_path=None):
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
            return name, VariableFactory.build(name, match.group('value'), vsection, base_path), match.group('assignType')
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
                var, val, assign = self.parse_variable(line, test.tags, vsection=sect, fail=fail,
                                                       base_path=getattr(test, "path", None))
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
            'result_as_variables': 'graph_result_as_variable',
            'y_group': 'graph_y_group',
            'graph_serie_sort':'graph_series_sort',
            'series_prop': 'graph_series_prop',
            'graph_legend_ncol': 'legend_ncol',
            'graph_legend_loc': 'legend_loc',
            'graph_do_legend' : 'graph_legend',
            'do_legend'     : 'graph_legend',
            'var_label_dir' : 'graph_label_dir',
            'graph_max_col' : 'graph_max_cols',

        }

        # All the options of the %config section, with their default value. They are documented in
        # npf-docs (tests.rst for the test options, regress.rst, graph.rst). Most options taking a list
        # or a dict per result type also accept "result" as a key, for all result types.

        # Environment
        self.__add("default_repo", "local")  # Repository used when none is given (e.g. npf-run without a repo)

        # Regression related
        self.__add_list("accept_zero", ["time", "DROP", "DROPPED", "DROPPEDPC", "LOST"])  # Result types (and time series namespaces) that may be 0. Other results at 0 are ignored, as an error
        self.__add("n_supplementary_runs", 3)  # Runs added when a regression is found, before telling about it
        self.__add("acceptable", 0.01)  # Accepted relative difference with the previous version (0.01 = 1%)
        self.__add("accept_outliers_mult", 1)  # Values further than this many standard deviations from the mean are outliers (regression, --graph-reject-outliers)
        self.__add("accept_variance", 1)  # Also accept a difference of this many standard deviations of the results, divided by the mean

        # Test related

        self.__add_list("time_kinds", [])  # Time series namespaces to take from the cache. Empty: all of them
        self.__add("n_runs", 3)  # Runs of each combination of variables
        self.__add("n_retry", 0)  # Times a run is retried when it fails, e.g. when a script does not give its results
        self.__add_dict("var_n_runs", {})  # {RESULT:N}: only keep the time series of RESULT for the N first runs
        self.__add_dict("var_markers", {}) #Do not set CDF here, small CDF may want them, and then scatterplot would not work. {RESULT:o;^}: markers of the lines of RESULT, per series
        self.__add("result_add", False)  # true, or a list of result types: when a script gives the same result several times, add the values
        self.__add("result_append", False)  # true, or a list of result types: keep all the values, as several points of the run
        self.__add("result_overwrite", False)  # true, or a list of result types: keep the last value
        self.__add_list("result_regex", [
            r"(:?(:?(?P<kind>[A-Z0-9_]+)-)?(?P<time_value>[0-9.]+)-)?RESULT(:?-(?P<type>[A-Z0-9_:~.@()-]+))?[ \t]+(?P<value>[-]?[0-9.]+(e[+-][0-9]+)?)[ ]*(?P<multiplier>[nµugmkKGT]?)(?P<unit>s|sec|b|byte|bits)?"])  # Regexes finding the results in the output of the scripts
        self.__add_list("results_expect", [])  # Result types that each run must give, else the run failed
        self.__add("autokill", True)  # When a script ends, stop the other scripts of the run. %script autokill=false overrides it
        self.__add("nokill", False)  # Do not stop this script at the end of the run, let it end by itself. %script nokill=true overrides it
        self.__add("critical", False)  # When a script fails, stop the whole test. %script critical=true overrides it
        self.__add_dict("env", {})  # Unimplemented yet
        self.__add("timeout", 30)  # Seconds after which the scripts of a run are stopped. %script timeout= overrides it
        self.__add("hardkill", 5000)  # Milliseconds a stopped script has to exit before it is killed. %script hardkill= overrides it

        # Role related
        self.__add_dict("default_role_map", {})  # {ROLE:OTHER}: a role that is not given with --cluster runs where OTHER runs
        self.__add_list("role_exclude", [])  # {A+B}: roles that must not run on the same node

        # Graph options
        self.__add_dict("graph_combine_variables", {})  # {A+B:AB}: combine variables A and B into a single variable AB
        self.__add_dict("graph_subplot_results", {})  # {A+B:2}: plot results A and B in one figure, with 2 columns or 2 axes (graph_subplot_type)
        self.__add("graph_subplot_variable", None)  # One subplot per value of this variable
        self.__add("graph_subplot_unique_legend", False)  # With graph_subplot_type=axis, one legend for all the axes
        self.__add_list("graph_display_statics", [])  # Add a subplot showing the values of the static variables
        self.__add_list("graph_variables_as_series", [])  # Variables that become series (lines)
        self.__add("graph_variables_explicit", False)  # Name the series made from a variable "VAR = value" instead of "value"
        self.__add_list("graph_hide_variables", [])  # Variables removed from the graphs and outputs, as if they were not dynamic
        self.__add_dict('graph_result_as_variable', {})  # {COUNT-Q(.*):QUEUE}: results matching the regex become values of a variable (also graph_result_as_variables)
        self.__add_dict('graph_map', {})  # {VAR:file}: replace the values of VAR with the map in file
        self.__add_dict('graph_map_inline', {})  # {regex:value}: replace the values of all variables matching regex with value
        self.__add_dict('graph_x_sort', {})  # true/false, or the X variables, to sort the X axis (default: only numerical variables)
        self.__add("graph_scatter", False)  # true, or result types: scatter plot instead of lines
        self.__add("graph_show_values", False)  # Write the values on the graph, with this number of decimals
        self.__add("graph_show_ylabel", True)  # true/false, or result types: show the label of the Y axis
        self.__add("graph_show_xlabel", True)  # true/false, or result types: show the label of the X axis
        self.__add("graph_x_label", True)  # Bar plots: false to hide the labels of the bar groups
        self.__add("graph_subplot_type", "subplot")  # subplot: one subplot per result of graph_subplot_results. axis: one Y axis per result, in one plot
        self.__add("graph_max_series", None)  # Keep only the N first series (see graph_series_sort)
        self.__add("graph_max_cols", 2)  # Maximum number of columns of subplots
        self.__add("graph_series_as_variables", False)  # The series become values of a variable, e.g. to use another variable as series
        self.__add("graph_series_prop", False)  # Divide the results by those of the first series, which is removed. A number: also multiply by it (100: percents)
        self.__add("graph_series_sort", None)  # Sort the series: natsort, avg, min, max. Prefix with - to reverse
        self.__add("graph_series_label", None)  # Name of the series, with variables replaced, e.g. "$CPU cores"
        self.__add_dict("graph_filter_by", {})  # {RESULT:FILTER}: draw RESULT dashed where FILTER is true, e.g. {THROUGHPUT:DROPPEDPC>0}
        self.__add("graph_filter_linestyle", "--")  # Line style of the parts that graph_filter_by filters
        self.__add("graph_filter_fillstyle", "none")  # Marker fill style of the parts that graph_filter_by filters
        self.__add_dict("graph_filter", {})  # {RESULT:expression of x}: keep only the values x of RESULT for which the expression is true, e.g. {LATENCY:x<1000}
        self.__add("graph_bar_stack", False)  # Bar plots: stack the bars of a group instead of putting them side by side
        self.__add("graph_bar_hatch", False)  # Bar plots: hatch the bars, with a pattern per series
        self.__add("graph_bar_inter", None)  # Bar plots: space between the groups of bars. Default: depends on the plot
        self.__add("graph_text",'')  # Text added under the graphs
        self.__add("graph_legend", None), #the default behavior depends upon the type of graph. true/false, or result types: show the legend
        self.__add_list("graph_labels", [])  # Labels of the legend, replacing the names of the series
        self.__add("graph_error_fill",False)  # Draw the confidence interval as a filled zone instead of error bars
        self.__add_dict("graph_error", {"CDF":"none"})  # {RESULT:type}: confidence interval of lines, bar (std. dev.), barminmax, fill, fillminmax, fill50 (25th-75th percentiles) or none
        self.__add("graph_mode",None)  # Unused
        self.__add_dict("graph_y_group",{})  # {RESULT:method}: how the values of the runs give a point: mean (default), median, min, max, perc95, std, n, first, last, all
        self.__add_list("graph_color", [])  # Color set of each series: 0 (several colors) to 5 (shades of one color)
        self.__add_list("graph_markers", ['o', '^', 's', 'D', '*', 'x', '.', '_', 'H', '>', '<', 'v', 'd'])  # Markers of the series, in order
        self.__add_list("graph_lines", ['-', '--', '-.', ':'])  # Line styles of the series, in order
        self.__add_dict("graph_line_params", {})  # {param:value}: arguments of matplotlib's plot() for lines, e.g. {linewidth:2}
        self.__add_list("legend_bbox", [0, 1, 1, .05])  # bbox_to_anchor of the legend when it is outside the graph (legend_loc=outer ...)
        self.__add("legend_loc", "best")  # Location of the legend (matplotlib's loc), or "outer ..." to put it outside of the graph
        self.__add("legend_mode", None)  # mode of matplotlib's legend(), e.g. expand
        self.__add_list("subplot_legend_loc", [])  # With graph_subplot_type=axis, location of the legend of each axis
        self.__add("graph_max_variables",3)  # When there are more dynamic variables, the least useful are removed
        self.__add_list("graph_keep_variables", [])  # Variables never removed by graph_max_variables

        self.__add("legend_frameon", True)  # Draw a frame around the legend
        self.__add("legend_ncol", 1)  # Number of columns of the legend. A list: per subplot
        self.__add("var_hide", {})  # Variables not shown when NPF prints the variables of a run
        self.__add_list("var_log", [])  # Variables and results drawn on a logarithmic axis
        self.__add_dict("var_log_base", {})  # {VAR:base}: base of the logarithmic axis (default 2)
        self.__add_dict("var_divider", {'result': 1})  # {VAR:N}: divide the values of a variable or result by N
        self.__add_dict("var_lim", {})  # {VAR:min-max}: range of an axis. Several ranges separated by + make a broken axis
        self.__add_dict("var_format", {})  # {VAR:format}: printf-like format of the values, or eng
        self.__add_dict("var_ticks", {})  # {VAR:0+5+10}: ticks of the axis

        self.__add_dict("graph_legend_params", {})  # Arguments of matplotlib's legend(), e.g. {frameon:0}
        self.__add_list("var_grid", ["result"])  # Variables and results that have a grid
        self.__add("graph_grid_linestyle", ":")  # Line style of the grid

        self.__add("graph_fillstyle", "full")  # Fill style of the markers
        self.__add_dict("graph_tick_params", {})  # Arguments of matplotlib's tick_params(), e.g. {direction:in}
        self.__add("var_serie",None)  # Variable used as series of a line plot
        self.__add_dict("var_names", {"result-LATENCY":"Latency (µs)", "result-THROUGHPUT":"Throughput", "^THROUGHPUT$":"Throughput", "boxplot":"", "^PARALLEL$":"Number of parallel connections", "^ZEROCOPY$":"Zero-Copy", "CDFLATPC":"CDF", "CDFLATVAL":"Latency"})  # {VAR:name}: names of variables and results on the graphs
        self.__add_dict("var_unit", {"result": "","result-LATENCY":"us","latency":"us","throughput":"bps"})  # {VAR:unit}: units of variables and results
        self.__add("graph_show_fliers", True)  # Box plots: show the outliers
        self.__add_dict("graph_cross_reference", {})  # {RESULT:VAR}: on the graph of RESULT, use VAR as X axis, e.g. the measured rate instead of the requested one
        self.__add_dict("graph_background", {})  # A color index, or {RESULT:index}: background color of the graph (true: index 15)
        self.__add_dict("var_round", {})  # {VAR:precision}: round the values of VAR, merging the runs that become equal
        self.__add_dict("var_aggregate", {})  # {VAR:method}: merge the values of VAR: all, mean, median, ...
        self.__add_dict("var_drawstyle", {})  # {RESULT:style}: drawstyle of matplotlib's plot(), e.g. steps-post
        self.__add_list("graph_type", [])  # Graph types: line, bar, simple_bar, barh, boxplot, cdf, heatmap, sparse_heatmap. {RESULT:type} per result
        self.__add_list("graph_only", [])  # Only draw the graphs of these results
        self.__add("title", None)  # Title of the graphs
        self.__add_list("require_tags", [])  # Tags the test needs: without them, it is skipped
        self.__add_dict("graph_label_dir", {})  # {VAR:direction}: direction of the labels of the X axis: vertical, horizontal, diagonal
        self.__add("graph_force_diagonal_labels", False)  # Always use diagonal labels on the X axis
        self.__add("graph_smooth", 1)  # Lines: smooth over N% of the X range (1: no smoothing)

        # Time series
        self.__add("time_precision", 1)  # Decimals of the time, to merge the values of close times
        self.__add("time_sync", False)  # true, or namespaces: time starts at 0 at the first non-zero value
        self.__add_list("glob_sync", [])  # Namespaces whose time is synchronized together
        self.__add_list("var_sync", ["time"])  # Variables synchronized on the graphs: the time series start at 0
        self.__add_dict("var_shift", {})  # {RESULT:shift}: shift the time of RESULT on the graphs
        self.__add_dict("var_repeat", {})  # Results repeated at each time, from their previous value, when they have no value there

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

