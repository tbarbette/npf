from lark import Lark, Transformer

variable_grammar = r"""
    start: (var_expr | TEXT)+

    var_expr: DOLLAR BRACE_OPEN NAME BRACE_CLOSE   -> var_braced
            | DOLLAR NAME                          -> var_simple

    TEXT: /[^$]+/ | "$"

    DOLLAR: "$"
    BRACE_OPEN: "{"
    BRACE_CLOSE: "}"

    NAME: /[a-zA-Z0-9._-]+/

    %import common.WS
    %ignore WS
"""

variable_parser = Lark(variable_grammar, start="start", parser="lalr")


class VariableSubstituter(Transformer):
    def __init__(self, variables):
        super().__init__()
        self.variables = variables

    def var_braced(self, items):
        varname = str(items[2])
        val = self.variables.get(varname)
        if val is not None:
            return str(val[0] if isinstance(val, tuple) else val)
        return "${" + varname + "}"

    def var_simple(self, items):
        varname = str(items[1])
        val = self.variables.get(varname)
        if val is not None:
            return str(val[0] if isinstance(val, tuple) else val)
        return "$" + varname

    def TEXT(self, item):
        return str(item)

    def start(self, items):
        return ''.join(items)


def substitute_variables(variables, content):
    try:
        tree = variable_parser.parse(content)
        substituter = VariableSubstituter(variables)
        return substituter.transform(tree)
    except Exception as e:
        print(f"Unexpected error in variable substitution: {e}")
        return content
