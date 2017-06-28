from npf.testie import Testie


class Module(Testie):
    def __init__(self, testie_path, options, tags=None, role=None):
        super().__init__(testie_path, options, tags, role)

