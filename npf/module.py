from npf.test import Test


class Module(Test):
    def __init__(self, test_path, options, parent, section, tags=None, role=None):
        if section.is_include:
            test_path = (parent.path +'/' if parent.path else '') + test_path
        super().__init__(test_path, options, tags, role)

