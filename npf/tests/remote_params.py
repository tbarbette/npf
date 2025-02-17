class RemoteParameters:
    default_role_map: dict
    role: str
    role_id: str
    script: object
    name: str
    delay: int
    executor: object

    def __init__(self):
        self.default_role_map = None
        self.role = None
        self.role_id = None
        self.script = None
        self.name = None
        self.delay = None
        self.executor = None
        self.bin_paths = None
        self.queue = None
        self.sudo = None
        self.autokill = None
        self.queue = None
        self.timeout = None
        self.options = None
        self.stdin = None
        self.commands = None
        self.testdir = None
        self.waitfor = None
        self.event = None
        self.title = None
        self.env = None
        self.virt = ""
        self.options = None

    pass