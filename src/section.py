from variable import *

class SectionFactory:
    @staticmethod
    def build(perf, data):
        sectionName=data[0].rstrip()
        if (sectionName == 'file'):
            s=SectionFile(data[1].rstrip())
        elif (len(data) > 1):
            raise Exception("Only file section takes arguments (" + s.name +" has argument " + data[1] + ")");
        elif (hasattr(perf,sectionName)):
            raise Exception("Only one section of type " + s.name + " is allowed")
        elif (sectionName == 'variables'):
            s = SectionVariable()
            setattr(perf,s.name,s)
        elif (sectionName == 'config'):
            s = SectionConfig()
            setattr(perf,s.name,s)
        else:
            s = Section(sectionName)
            setattr(perf,s.name,s)
        return s

class Section:
    def __init__(self, name):
        self.name = name
        self.content = ''

    def finish(self, perf):
        pass

class SectionConfig(Section):
    def __init__(self):
        self.name = 'config'
        self.content = ''

        self.acceptable = 0.01
        self.n_runs=1
        self.unacceptable_n_runs=3

    def finish(self, perf):
        if (self.content):
            for line in self.content.split("\n"):
                if not line:
                    continue
                var = line.split('=')
                val = var[1].strip()
                if is_numeric(val):
                    val = float(val)
                    if val.is_integer():
                        val = int(val)
                setattr(self,var[0],val)

class SectionFile(Section):
    def __init__(self,filename):
        self.name = 'file'
        self.content = ''
        self.filename = filename

    def finish(self, perf):
        perf.files.append(self)

class BruteVariableExpander():
    """Expand all variables building the full
    matrix first."""
    def __init__(self,vsec):
        self.vsec = vsec
        self.expanded = [dict()]

        if (self.vsec.content):
            vs=[]
            for line in self.vsec.content.split("\n"):
                if not line:
                    continue
                var = line.split('=')
                vs.append(VariableFactory.build(var[0],var[1]))

            for v in vs:
                newList=[]
                for nvalue in v.makeValues():
                    for ovalue in self.expanded:
                        z = ovalue.copy()
                        z.update(nvalue)
                        newList.append(z)
                self.expanded = newList
        self.it = self.expanded.__iter__()


    def next(self):
        return self.it.next()

class SectionVariable(Section):
    def __init__(self):
        self.name = 'variables'
        self.content = ''

    def __iter__(self):
        return BruteVariableExpander(self)

    def finish(self, perf):
        pass

