from variable import *
from collections import OrderedDict

sections=['info','config','variables','script','file']

class SectionFactory:
    @staticmethod
    def build(perf, data):
        sectionName=data[0].rstrip()
        if not sectionName in sections:
            raise Exception("Unknown section %s" % sectionName);
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
    def __init__(self,vlist):
        self.expanded = [OrderedDict()]
        for k,v in vlist.iteritems():
            newList=[]
            for nvalue in v.makeValues():
                for ovalue in self.expanded:
                    z = ovalue.copy()
                    z.update({k:nvalue})
                    newList.append(z)
            self.expanded = newList
        self.it = self.expanded.__iter__()


    def next(self):
        return self.it.next()

class SectionVariable(Section):
    def __init__(self):
        self.name = 'variables'
        self.content = ''
        self.vlist=OrderedDict()

    def __iter__(self):
        return BruteVariableExpander(self.vlist)

    def dynamics(self):
        """List of non-constants variables"""
        dyn = OrderedDict()
        for k,v in self.vlist.iteritems():
            if v.count()>1: dyn[k] = v
        return dyn

    def finish(self, perf):
        for line in self.content.split("\n"):
            if not line:
                continue
            pair = line.split('=')
            var = pair[0].split(':')

            if len(var) == 1:
                var = var[0]
            else:
                if ((var[0] in perf.tags) or (var[0].startswith('-') and not var[0][1:] in perf.tags)):
                    var = var[1]
                else:
                    continue

            self.vlist[var] = VariableFactory.build(var,pair[1])


class SectionConfig(SectionVariable):

    def __add(self, var , val):
        self.vlist[var] = SimpleVariable(var,val)

    def __init__(self):
        self.name = 'config'
        self.content = ''
        self.vlist={}
        self.__add("acceptable", 0.01)
        self.__add("n_runs", 1)
        self.__add("unacceptable_n_runs", 3)

    def varname(self,key):
        if (key in self["varnames"]):
            return self["varnames"][key]
        else:
            return key

    def __getitem__(self,key):
        var = self.vlist[key]
        v = var.makeValues()[0]
        return v

