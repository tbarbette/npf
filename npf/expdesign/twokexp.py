from collections import OrderedDict

from npf.expdesign.fullexp import FullVariableExpander

class TWOKVariableExpander(FullVariableExpander):
    """Only explore max and min value of each dimension"""

    def __init__(self, vlist, overriden):      
         #List of all variables
        self.expanded = [OrderedDict()]
        for k, v in vlist.items():
            if k in overriden:
                continue
            newList = []
            l = v.makeValues()

            if len(l) > 2:
                l = [l[0],l[-1]]
                
            # For every of those two values we duplicate all existing runs
            for nvalue in l:
                for ovalue in self.expanded:
                    z = ovalue.copy()
                    z.update(nvalue if type(nvalue) is OrderedDict else {k: nvalue})
                    newList.append(z)

            self.expanded = newList
        self.it = self.expanded.__iter__()  

    def strlen(self):
        return f"{len(self.expanded)}"
