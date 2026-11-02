"""Faux module adsk, juste assez pour charger l'add-in et jouer run() / stop() hors de Fusion."""
import sys
import types


class _Base:
    def __init__(self, *a, **k):
        pass


class _Evenement:
    def __init__(self):
        self.handlers = []

    def add(self, h):
        self.handlers.append(h)
        return True

    def remove(self, h):
        self.handlers.remove(h)
        return True


class _Controle:
    isPromoted = False

    def __init__(self, parent, id_):
        self.parent, self.id = parent, id_

    def deleteMe(self):
        self.parent.pop(self.id, None)
        return True


class _Controles:
    def __init__(self):
        self.d = {}

    def itemById(self, i):
        return self.d.get(i)

    def addCommand(self, definition, *a):
        self.d[definition.id] = _Controle(self.d, definition.id)
        return self.d[definition.id]


class _Panneau:
    def __init__(self, tous=None, id_=None):
        self.controls = _Controles()
        self.tous, self.id = tous, id_

    def deleteMe(self):
        self.tous.pop(self.id, None)
        return True


class _PanneauxEspace:
    def __init__(self, tous, hote):
        self.tous, self.hote = tous, hote

    def add(self, id_, nom, *a):
        self.tous[id_] = _Panneau(self.tous, id_)
        self.tous[id_].hote = self.hote
        return self.tous[id_]


class _Onglet:
    def __init__(self, id_, nom, tous):
        self.id, self.name = id_, nom
        self.toolbarPanels = _PanneauxEspace(tous, id_)


class _Onglets:
    def __init__(self, l):
        self.l, self.count = l, len(l)

    def item(self, i):
        return self.l[i]


class _Espace:
    def __init__(self, id_, nom, tous):
        self.id, self.name = id_, nom
        self.toolbarPanels = _PanneauxEspace(tous, id_)
        self.toolbarTabs = _Onglets([_Onglet("ToolsTab", "OUTILS", tous), _Onglet("AnimationTab", "ANIMATION", tous)])


class _Espaces:
    def __init__(self, tous):
        self.l = [_Espace("FusionSolidEnvironment", "Design", tous),
                  _Espace("FusionAnimationEnvironment", "Animation", tous)]
        self.count = len(self.l)

    def item(self, i):
        return self.l[i]


class _Panneaux:
    def __init__(self):
        self.d = {"SolidScriptsAddinsPanel": _Panneau()}

    def itemById(self, i):
        return self.d.get(i)


class _ControlDefinition:
    name = ""


class _Definition:
    def __init__(self, parent, id_, nom, ressources):
        self.parent, self.id, self.ressources = parent, id_, ressources
        self.commandCreated = _Evenement()
        self.controlDefinition = _ControlDefinition()

    def deleteMe(self):
        self.parent.pop(self.id, None)
        return True


class _Definitions:
    def __init__(self):
        self.d = {}

    def itemById(self, i):
        return self.d.get(i)

    def addButtonDefinition(self, id_, nom, info, ressources=""):
        self.d[id_] = _Definition(self.d, id_, nom, ressources)
        return self.d[id_]


class _UI:
    def __init__(self):
        self.commandDefinitions = _Definitions()
        self.allToolbarPanels = _Panneaux()
        self.workspaces = _Espaces(self.allToolbarPanels.d)
        self.activeCommand = "SelectCommand"
        self.messages = []

    def messageBox(self, *a):
        self.messages.append(a)


class _App:
    version = "faux"

    def __init__(self):
        self.userInterface = _UI()
        self.evenements = {}
        self.tirs = 0
        self.activeViewport = None
        self.activeProduct = None

    def registerCustomEvent(self, i):
        self.evenements[i] = _Evenement()
        return self.evenements[i]

    def unregisterCustomEvent(self, i):
        return self.evenements.pop(i, None) is not None

    def fireCustomEvent(self, i, data=""):
        self.tirs += 1
        return False  # comme Fusion : False alors que l'événement est en file


APP = None


def installer():
    global APP
    APP = _App()
    adsk = types.ModuleType("adsk")
    core = types.ModuleType("adsk.core")
    fusion = types.ModuleType("adsk.fusion")
    core.Application = types.SimpleNamespace(get=lambda: APP)
    core.CustomEventHandler = _Base
    core.CommandCreatedEventHandler = _Base
    core.InputChangedEventHandler = _Base
    core.CommandEventHandler = _Base
    core.DefaultModelingOrientations = types.SimpleNamespace(YUpModelingOrientation=0,
                                                             ZUpModelingOrientation=1)
    fusion.Design = types.SimpleNamespace(cast=lambda o: None)
    adsk.core, adsk.fusion = core, fusion
    sys.modules.update({"adsk": adsk, "adsk.core": core, "adsk.fusion": fusion})
    return APP
