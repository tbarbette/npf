from npf import npf
from npf.sections import *
from npf.variable import *

from spellwise import Editex

import re

known_sections = ['info', 'config', 'variables', 'exit', 'pypost' , 'pyexit', 'late_variables', 'include', 'file', 'require', 'import', 'script', 'init', 'exit']

class SpellChecker:
    def __init__(self) -> None:
        self.algorithm = Editex()

    def add_words(self, d):
        self.algorithm.add_words(d)

    def suggest(self, w, max = None):
        suggestions = self.algorithm.get_suggestions(w)
        if len(suggestions) > 1:
            return suggestions[0]["word"]

hu = SpellChecker()
hu.add_words(known_sections)

class SectionFactory:
    varPattern = "([a-zA-Z0-9_:-]+)[=](" + Variable.VALUE_REGEX + ")?"
    namePattern = re.compile(
        "^(?P<tags>" + Variable.TAGS_REGEX + "[:])?(?P<name>info|"
        "config|"
        "variables|"
        "exit|"
        "pypost|"
        "pyexit(:?\\s+(?P<PyExitName>.*))?|"
        "late_variables|"
        "include\\s+(?P<includeName>[a-zA-Z0-9_./-]+)(?P<includeParams>([ \t]+" + varPattern + ")+)?|"
        "(init-)?file(:?[@](?P<fileRole>[a-zA-Z0-9]+))?\\s+(?P<fileName>[a-zA-Z0-9_.${}-]+)(:? (?P<fileNoparse>noparse))?(:? (?P<fileJinja>jinja))?|"
        "require(:?\\s+(?P<requireJinja>jinja))?|"
        "import(:?[@](?P<importRole>[a-zA-Z0-9]+)(:?[-](?P<importMulti>[*0-9]+))?)?[ \t]+(?P<importModule>" + Variable.VALUE_REGEX + ")(?P<importParams>([ \t]+" + varPattern + ")+)?|"
        "sendfile(:?[@](?P<sendfileRole>[a-zA-Z0-9]+))?\\s+(?P<sendfilePath>.*)|" +
        "(:?script|init|exit)(:?[@](?P<scriptRole>[a-zA-Z0-9]+)(:?[-](?P<scriptMulti>[*0-9]+))?)?(:? (?P<scriptJinja>jinja))?(?P<scriptParams>([ \t]+" + varPattern + ")*))$")

    @staticmethod
    def build(test, data):
        """
        Create a section from a given header
        :param test: The parent script
        :param data: Array containing the section name and possible arguments
        :return: A Section object
        """
        matcher = SectionFactory.namePattern.match(data)
        if not matcher:
            s = hu.suggest(data)
            if s:
                raise Exception("Unknown section line '%s'. Did you mean %s ?" % (data,s))
            else:
                raise Exception("Unknown section line '%s'." % (data))


        if not SectionVariable.match_tags(matcher.group('tags'), test.tags):
            return SectionNull()
        sectionName = matcher.group('name')

        s = None

        if sectionName.startswith('import'):
            params = matcher.group('importParams')
            module = matcher.group('importModule')
            params = dict(re.findall(SectionFactory.varPattern, params)) if params else {}
            s = SectionImport(matcher.group('importRole'), module, params)
            multi = matcher.group('importMulti')
            s.multi = multi
            return s

        if sectionName.startswith('sendfile'):
            s = SectionSendFile(matcher.group('sendfileRole'), matcher.group('sendfilePath'))
            return s

        if sectionName.startswith('script') or sectionName.startswith('exit') or (
                sectionName.startswith('init') and not sectionName.startswith('init-file')):
            params = matcher.group('scriptParams')
            params = dict(re.findall(SectionFactory.varPattern, params)) if params else {}

            s = SectionScript(matcher.group('scriptRole'), params, jinja=matcher.group('scriptJinja'))
            multi = matcher.group('scriptMulti')
            s.multi = multi
            if sectionName.startswith('init'):
                s.type = SectionScript.TYPE_INIT
                s.params.setdefault("autokill", False)
            if sectionName.startswith('exit'):
                s.type = SectionScript.TYPE_EXIT

            return s

        if sectionName.startswith('pyexit'):
            pg = matcher.group("PyExitName")
            if pg:
                name = pg.strip()
            else:
                name = ""
            s = SectionPyExit(name)
            return s

        if matcher.group('scriptParams') is not None:
            raise Exception("Only script sections takes arguments (" + sectionName + " has argument " +
                            matcher.groups("params") + ")")

        if sectionName.startswith('file'):
            s = SectionFile(matcher.group('fileName').strip(), role=matcher.group('fileRole'),
                            noparse=matcher.group('fileNoparse'), jinja=matcher.group('fileJinja'))
            return s
        if sectionName.startswith('init-file'):
            s = SectionInitFile(matcher.group('fileName').strip(), role=matcher.group('fileRole'),
                                noparse=matcher.group('fileNoparse'))
            return s
        elif sectionName.startswith('include'):
            params = matcher.group('includeParams')
            params = dict(re.findall(SectionFactory.varPattern, params)) if params else {}
            s = SectionImport(None, matcher.group('includeName').strip(), params, is_include=True)
            return s
        elif sectionName == 'require':
            s = SectionRequire(jinja=matcher.group('requireJinja'))
            return s
        elif sectionName == 'late_variables':
            s = SectionLateVariable()
            return s
        if hasattr(test, sectionName):
            raise Exception("Only one section of type " + sectionName + " is allowed")

        if sectionName == 'variables':
            s = SectionVariable()
        elif sectionName == 'pypost':
            s = Section('pypost')
        elif sectionName == 'exit':
            s = Section('exit')
        elif sectionName == 'config':
            s = SectionConfig()
        elif sectionName == 'info':
            s = Section('info')
        if s is None:
            raise Exception("Unknown section %s, did you meant %s?" % sectionName, hu.suggest(sectionName))
        setattr(test, s.name, s)
        return s


