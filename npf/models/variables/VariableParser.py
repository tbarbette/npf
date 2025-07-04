from lark import Lark, Transformer

variable_grammar = r"""
    start: (var_expr | TEXT)+

    var_expr: DOLLAR BRACE_OPEN NAME BRACE_CLOSE                                    -> var_braced
            | DOLLAR BRACE_OPEN NAME COLON INT COLON NAME BRACE_CLOSE               -> var_role
            | DOLLAR NAME                                                           -> var_simple
            | PY_EXPR                                                               -> var_py_replacement

    PY_EXPR: /\$\(\((.|\n)*?\)\)/

    TEXT: /[^$]+/ | "$"

    DOLLAR: "$"
    BRACE_OPEN: "{"
    BRACE_CLOSE: "}"
    COLON: ":"

    NAME: /[a-zA-Z0-9_-]+/
    INT: /[0-9]+/

    %import common.WS
    %ignore WS
"""

variable_parser = Lark(variable_grammar, start="start", parser="lalr", lexer="contextual")

class VariableSubstituter(Transformer):
    def __init__(self, variables):
        super().__init__()
        self.variables = variables

    def var_braced(self, items):
        varname = str(items[2])
        val = self.variables.get(varname)
        return str(val[0] if isinstance(val, tuple) else val) if val is not None else "${" + varname + "}"

    def var_simple(self, items):
        varname = str(items[1])
        val = self.variables.get(varname)
        return str(val[0] if isinstance(val, tuple) else val) if val is not None else "$" + varname

    def var_role(self, items):
        return ''.join(items)

    def var_py_replacement(self, items):
        py_expr = str(items[0])
        inner = py_expr[3:-2].strip()
        substituted_inner = substitute_variables(self.variables, inner)
        return f"$(( {substituted_inner} ))"

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
        raise Exception(f"Unexpected error in variable substitution: {e}")