"""Grammar of the literal values of NPF variables: ranges, sets, CONCAT() and FILE().

    VAR=[1-10]  [1-10#2]  [1*1024]  [[0-1#0.25]]        ranges ([[ ]] forces integers)
    VAR={a,b,c}                                          a list
    VAR={1:Zero-copy,0:Copy}                             values with a label (scripts get 1 and 0)
    VAR={"https://a.org/x?y=1,2","b c"}                  quoted values may contain , : { } and spaces
    VAR={https://a.org/,https://b.org/}                  "://" never separates a value from its label,
    VAR={https://www.debian.org/:Debian}                 so URLs need no quotes
    VAR=FILE(sites.txt)                                  one value per line, # comments and blank lines ignored
    VAR=CONCAT({1,2},[4-8],FILE(more.txt))               values of all arguments, in order

Unquoted text is kept as written, spaces included, as before this grammar existed. A set or range may be followed
by spaces and a // or # comment. Values that are none of the above are not parsed here (simple values, and the
EXPAND/RANDOM/HEAD/IF templates of VariableFactory).
"""
import os
import re
from collections import OrderedDict

from lark import Lark, Transformer, UnexpectedInput, v_args
from lark.exceptions import VisitError

VALUE_GRAMMAR = r"""
    start: _value _TRAILER?

    _value: range | set | concat | file

    range: "[" NUMBER RANGE_OP NUMBER step? "]"
         | "[" "[" NUMBER RANGE_OP NUMBER step? "]" "]"   -> int_range
    step: "#" NUMBER?

    set: "{" entry ("," entry)* "}"
    entry: item                    -> plain
         | item ":" vitem          -> keyed
    item: _WS? STRING _WS? | TEXT |
    vitem: _WS? STRING _WS? | VTEXT |

    concat: "CONCAT(" arg ("," arg)* ")"
    arg: _WS? (range | set | concat | file | STRING | ARGTEXT) _WS?

    file: "FILE(" _WS? (STRING | PATH) _WS? ")"

    NUMBER: /-?[0-9.]+/
    RANGE_OP: /[-+*,]/
    STRING.3: /"(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*'/
    // Unquoted text, kept verbatim. It cannot start with a quote (after spaces), ${...} may contain : , { }
    // and "://" (URLs) is not a key separator.
    TEXT.2: /(?![ \t]*["'])(?:\$\{[^{}\n]*\}|:\/\/|[^,:{}\n])+/
    VTEXT.2: /(?![ \t]*["'])(?:\$\{[^{}\n]*\}|[^,{}\n])+/
    ARGTEXT.2: /(?![ \t]*["'\[{])(?:\([^()\n]*\)|[^,()\n])+/
    PATH.2: /(?![ \t]*["'])[^()"'\n]+/
    _WS: /[ \t]+/
    _TRAILER: /[ \t]+(?:(?:\/\/|#).*)?|(?:\/\/|#).*/
"""

_parser = Lark(VALUE_GRAMMAR, start="start", parser="lalr", propagate_positions=True)

_STARTS = re.compile(r"^(\{(?!\{)|\[|CONCAT\(|FILE\()")


class VariableSyntaxError(ValueError):
    pass


def unquote(s: str) -> str:
    return re.sub(r"\\(.)", r"\1", s[1:-1])


def read_list_file(path: str, base_path=None):
    """The values of FILE(path): one per line, stripped, without blank lines and lines starting with #."""
    path = os.path.expanduser(path)
    candidates = [path] if os.path.isabs(path) else \
        [os.path.join(base_path, path)] * (base_path is not None) + [os.path.abspath(path)]
    for p in candidates:
        if os.path.isfile(p):
            with open(p) as f:
                values = [l.strip() for l in f.read().splitlines()]
            return [v for v in values if v and not v.startswith("#")]
    raise VariableSyntaxError("FILE(%s): no such file (looked for %s)" % (path, ", ".join(candidates)))


class _Values(Transformer):
    """Turns the parse tree in Variable objects."""

    def __init__(self, name, text, base_path, vsection):
        super().__init__()
        self.name = name
        self.text = text
        self.base_path = base_path
        self.vsection = vsection

    def start(self, items):
        return items[0]

    def _range(self, items, force_int):
        from npf.models.variables.RangeVariable import RangeVariable
        a, op, b = items[0], items[1], items[2]
        step = items[3] if len(items) > 3 else None
        return RangeVariable(self.name, str(a), str(b), str(op) == "*", step=step, force_int=force_int)

    def range(self, items):
        return self._range(items, False)

    def int_range(self, items):
        return self._range(items, True)

    def step(self, items):
        from npf.models.units import get_numeric
        # "[0-10#]": no step, the values come from the experimental design
        return get_numeric(str(items[0])) if items else ""

    def item(self, items):
        if not items:
            return ""
        t = items[0]
        return unquote(str(t)) if t.type == "STRING" else str(t)

    vitem = item

    @v_args(meta=True)
    def plain(self, meta, items):
        return None, items[0], meta

    @v_args(meta=True)
    def keyed(self, meta, items):
        return items[0], items[1], meta

    def set(self, entries):
        from npf.models.variables.DictVariable import DictVariable
        from npf.models.variables.ListVariable import ListVariable
        if len(entries) == 1 and entries[0][0] is None and entries[0][1] == "":
            return DictVariable(self.name, {})
        if all(k is not None for k, _, _ in entries):
            return DictVariable(self.name, OrderedDict((k, v) for k, v, _ in entries))
        if any(k is not None for k, _, _ in entries):
            # Some entries have a key, others not: as before, a list where "key:value" is a value
            return ListVariable(self.name, [v if k is None else self._source(m) for k, v, m in entries])
        return ListVariable(self.name, [v for _, v, _ in entries])

    def _source(self, meta):
        return self.text[meta.start_pos:meta.end_pos] if not getattr(meta, "empty", False) else ""

    def arg(self, items):
        from npf.models.variables.VariableFactory import VariableFactory
        from npf.models.variables.variable import Variable
        v = items[0]
        if isinstance(v, Variable):
            return v
        if v.type == "STRING":
            return VariableFactory.build(self.name, unquote(str(v)), self.vsection, self.base_path)
        return VariableFactory.build(self.name, str(v).strip(), self.vsection, self.base_path)

    def concat(self, args):
        from npf.models.variables.ParentVariable import ParentVariable
        return ParentVariable(self.name, args)

    def file(self, items):
        from npf.models.variables.ListVariable import ListVariable
        t = items[0]
        path = unquote(str(t)) if t.type == "STRING" else str(t).strip()
        values = read_list_file(path, self.base_path)
        if not values:
            raise VariableSyntaxError("FILE(%s) for variable %s has no value" % (path, self.name))
        return ListVariable(self.name, values)


def parse_value(name: str, text: str, vsection=None, base_path=None):
    """The Variable for a literal value, or None if text is not a range, set, CONCAT() or FILE().

    :param base_path: folder relative FILE() paths are searched in first (the folder of the test), then the
                      current folder
    :raises VariableSyntaxError: for a value that starts like a set or function but is not valid
    """
    if not _STARTS.match(text):
        return None
    try:
        tree = _parser.parse(text)
    except UnexpectedInput as e:
        if text.startswith("["):
            return None  # Many simple values start with [ (Click ports, arrays...)
        raise VariableSyntaxError("Invalid value for variable %s at column %d:\n  %s\n  %s^" %
                                  (name, e.column, text, " " * (e.column - 1))) from None
    try:
        return _Values(name, text, base_path, vsection).transform(tree)
    except VisitError as e:
        raise e.orig_exc from None
