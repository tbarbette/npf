import re

from colorama import Fore, Back, Style

foreColors = [Fore.CYAN, Fore.RED, Fore.GREEN, Fore.YELLOW, Fore.BLUE, Fore.MAGENTA]

class Executor:

    index = 0
    # Whether the output of a script is read while it runs. When it is not, its EVENT lines are only seen once it
    # ends, so a script waiting for them (waitfor=) may wait until the timeout.
    live_output = True

    def __init__(self):
        from npf import globals
        if globals.options.color:
            self.color = foreColors[Executor.index % len(foreColors)]
        else:
            self.color = ""
        Executor.index = Executor.index + 1
        self.path = None

    def get_env_str(self, env, options):
        import os
        import npf.globals
        if self.path:
            env['NPF_ROOT'] = self.path
            env['NPF_CWD_PATH'] = os.path.relpath(npf.globals.cwd_path(options), self.path)
            env['NPF_EXPERIMENT_PATH'] = '../' + os.path.relpath(npf.globals.experiment_path(), self.path)
            env['NPF_ROOT_PATH'] = '../' + os.path.relpath(npf.globals.npf_root_path(), self.path)

        import shlex
        env_str = ""
        for k, v in env.items():
            if v is not None:
                env_str += 'export ' + str(k) + '=' + shlex.quote(str(v)) + '\n'
        return env_str

    def searchEvent(self, output, eb, skip=0):
        """Posts the EVENTs of output, but the first skip ones. :return: the number of EVENTs in output"""
        results = re.findall("EVENT ([a-zA-Z_-]+)", output)
        for result in results[skip:]:
            eb.post(result)
        return len(results)

    def _print(self, title, line, nl = True):
        try:
            print(self.color + title + (Style.RESET_ALL if self.color else '') + ' ' + line, end=None if nl else '')
        except UnicodeEncodeError:
            print("Line ignored due to invalid encoding")

