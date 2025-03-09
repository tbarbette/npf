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


import regex
import re


class VariableFactory:
    @staticmethod
    def build(name, valuedata, vsection=None):
        result = re.match("(?P<doubleopen>\[?)\[(?P<a>-?[0-9.]+)(?P<log>[+-]|[*]|[,])(?P<b>-?[0-9.]+)(?P<step>[#][0-9.]*)?\](?P<doubleclose>\]?)", valuedata)
        if result:
            return RangeVariable(name, result.group('a'), result.group('b'), result.group('log') == "*", step= (get_numeric(result.group('step')[1:]) if result.group('step') else None), force_int=result.group('doubleopen')=='[')

        result = regex.match("\{([^:]*:[^,:]+)(?:(?:,)([^,:]*:[^,:]+))*\}", valuedata)
        if result:
            return DictVariable(name, result.captures(1) + result.captures(2))

        result = regex.match("\{([^,]+)(?:(?:,)([^,]*))*}", valuedata)
        if result:
            return ListVariable(name, result.captures(1) + result.captures(2))
        if valuedata.strip() == "{}":
            return DictVariable(name, {})

        result = regex.match("EXPAND\((.*)\)", valuedata)
        if result:
            if vsection is None:
                raise Exception("EXPAND variable without vsection",vsection)
            return ExpandVariable(name, result.group(1), vsection)

        result = regex.match("CONCAT\((.*),(.*)\)", valuedata)
        if result:
            return ParentVariable(name, [VariableFactory.build(name,result.group(1),vsection), VariableFactory.build(name,result.group(2),vsection)])

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