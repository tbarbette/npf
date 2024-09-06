from npf.variable import OrderedDict


from collections import OrderedDict


class FullVariableExpander:
    """Expand all variables building the full
    matrix first."""

    def __init__(self, vlist, overriden):
        self.expanded = [OrderedDict()]
        for k, v in vlist.items():
            if k in overriden:
                continue
            newList = []
            l = v.makeValues()

            # For every of those new values we duplicate all existing runs
            for nvalue in l:
                for ovalue in self.expanded:
                    z = ovalue.copy()
                    z.update(nvalue if type(nvalue) is OrderedDict else {k: nvalue})
                    newList.append(z)

            self.expanded = newList
        self.it = self.expanded.__iter__()

    def __iter__(self):
        return self.expanded.__iter__()

    def __next__(self):
        return self.it.__next__()
    
    def __len__(self):
        return len(self.expanded)

    def strlen(self):
        return len(self)