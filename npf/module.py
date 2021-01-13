from npf.testie import Testie


class Module(Testie):
    def __init__(self, testie_path, options, parent, section, tags=None, role=None):
        if section.is_include:
            testie_path = (parent.path +'/' if parent.path else '') + testie_path
        super().__init__(testie_path, options, tags, role)

