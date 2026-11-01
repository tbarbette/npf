from npf.models.units import get_numeric
from npf.models.variables.ParentVariable import ParentVariable
from npf.models.variables.DictVariable import DictVariable
from npf.models.variables.ExpandVariable import ExpandVariable
from npf.models.variables.HeadVariable import HeadVariable
from npf.models.variables.IfVariable import IfVariable
from npf.models.variables.ListVariable import ListVariable
from npf.models.variables.RandomVariable import RandomVariable
from npf.models.variables.RangeVariable import RangeVariable
from npf.models.variables.SimpleVariable import SimpleVariable
from npf.models.variables.grammar import parse_value


import regex
import re


class VariableFactory:
    @staticmethod
    def build(name, valuedata, vsection=None, base_path=None):
        """Builds the variable for a value, see npf/models/variables/grammar.py for ranges, sets, CONCAT() and FILE().

        :param base_path: folder of the test, where relative FILE() paths are searched first
        """
        var = parse_value(name, valuedata, vsection, base_path)
        if var is not None:
            return var

        result = regex.match("EXPAND\((.*)\)", valuedata)
        if result:
            if vsection is None:
                raise Exception("EXPAND variable without vsection",vsection)
            return ExpandVariable(name, result.group(1), vsection)

        result = regex.match("RANDOM[ ]*\([ ]*([^,]+)[ ]*,[ ]*([^,]+)[ ]*\)", valuedata)
        if result:
            if vsection is None:
                raise Exception("RANDOM variable without vsection",vsection)
            return RandomVariable(name, vsection.replace_all(result.group(1))[0], vsection.replace_all(result.group(2))[0])

        result = regex.match("HEAD[ ]*\([ ]*([^,]+)[ ]*,[ ]*\$([^,]+)[ ]*(,[ ]*(?P<sep>.+)[ ]*)?\)", valuedata)
        if result:
            if vsection is None:
                raise Exception("HEAD variable without vsection",vsection)
            nums = vsection.replace_all(result.group(1))[0].strip()
            return HeadVariable(name, nums,
                                vsection.vlist[result.group(2)].makeValues(), result.group('sep'))
        result = regex.match("IF[ ]*\([ ]*([^,]+)[ ]*,[ ]*([^,]+)[ ]*,[ ]*([^,]+)[ ]*\)", valuedata)
        if result:
            if vsection is None:
                raise Exception("IF variable without vsection",vsection)
            return IfVariable(name, vsection.replace_all(result.group(1))[0], result.group(2), result.group(3))

        return SimpleVariable(name, valuedata)