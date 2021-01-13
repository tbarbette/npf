import re

from colorama import Fore, Back, Style

foreColors = [Fore.BLACK, Fore.RED, Fore.GREEN, Fore.YELLOW, Fore.BLUE, Fore.MAGENTA, Fore.CYAN, Fore.WHITE]

class Executor:

    index = 0

    def __init__(self):
        self.color = foreColors[Executor.index % len(foreColors)]
        Executor.index = Executor.index + 1
        self.path = None

    def searchEvent(self, output, eb):
        results = re.finditer("EVENT ([a-zA-Z_-]+)", output)
        for result in results:
            eb.post(result.group(1))

    def _print(self, title, line, nl = True):
        try:
            print(self.color + title + Style.RESET_ALL + ' ' + line, end=None if nl else '')
        except UnicodeEncodeError:
            print("Line ignored due to invalid encoding")

