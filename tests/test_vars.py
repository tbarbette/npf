import unittest
from . import logger
from npf.models.variables.RangeVariable import RangeVariable
from npf.models.variables.SimpleVariable import SimpleVariable
from npf.models.variables.VariableParser import substitute_variables

def test_var_parser():
    def test_simple_var():
        variables = {"foo": "bar"}
        content = "Hello $foo!"
        result = substitute_variables(variables, content)
        assert result == "Hello bar!"

    def test_braced_var():
        variables = {"foo": "bar"}
        content = "Hello ${foo}!"
        result = substitute_variables(variables, content)
        assert result == "Hello bar!"

    def test_var_parser_inner():
        variables = {
            "foo": 123,
            "bar": ("hello",),
            "baz": 42,
        }
        content = "Value is $foo and ${bar}, missing $unknown stays same."
        result = substitute_variables(variables, content)
        assert result == "Value is 123 and hello, missing $unknown stays same."

    test_simple_var()
    test_braced_var()
    test_var_parser_inner()