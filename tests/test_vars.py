import unittest
from . import logger
from npf.models.variables.RangeVariable import RangeVariable
from npf.models.variables.SimpleVariable import SimpleVariable
from npf.models.variables.VariableParser import substitute_variables

class TestVariableParser(unittest.TestCase):
    def test_simple_var(self):
        variables = {"foo": "bar"}
        content = "Hello $foo!"
        result = substitute_variables(variables, content)
        assert result == "Hello bar!"

    def test_braced_var(self):
        variables = {"foo": "bar"}
        content = "Hello ${foo}!"
        result = substitute_variables(variables, content)
        assert result == "Hello bar!"

    def test_var_parser_inner(self):
        variables = {
            "foo": 123,
            "bar": ("hello",),
            "baz": 42,
        }
        content = "Value is $foo and ${bar}, missing $unknown stays same."
        result = substitute_variables(variables, content)
        assert result == "Value is 123 and hello, missing $unknown stays same."

    def test_var_parser_py_replacement(self):
        variables = {
            " not( )": "ERROR",
            "not": "ERROR",
        }
        content = "This should $(( not( ))) be replaced"
        result = substitute_variables(variables, content)
        assert result == content

    def test_var_role(self):
        variables = {
            " not( )": "ERROR",
            "not": "ERROR",
        }
        content = "This should ${self:0:pci} not be replaced"
        result = substitute_variables(variables, content)
        assert result == content

    def test_complex_01(self):
        content = 'echo "RESULT $(( ($X + 1) * ($ENORMOUS + $HUGE + $BIG + $SMALL) ))" '
        variables = {
            "ENORMOUS": 1000,
            "HUGE": 100,
            "BIG": 10,
            "SMALL": 1,
            "X" : 3
        }
        result = substitute_variables(variables, content)
        assert result == "RESULT $(( (3 + 1) * (1000 + 100 + 10 + 1) ))"