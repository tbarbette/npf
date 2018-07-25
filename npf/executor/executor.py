import re

class Executor:
    def searchEvent(self, output, eb):
        results = re.finditer("EVENT ([a-zA-Z_-]+)", output)
        for result in results:
            eb.post(result.group(1))


