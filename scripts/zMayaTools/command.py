from pymel import core as pm
from maya import OpenMaya as om
from maya import OpenMayaMPx as ompx

from zMayaTools import maya_logging
log = maya_logging.get_log()

class Command(ompx.MPxCommand):
    """
    A base class for MPxCommands.
    """
    @classmethod
    def register(cls, plugin):
        plugin.registerCommand(cls.cmd, cls.create, cls.create_syntax)

    @classmethod
    def deregister(cls, plugin):
        plugin.deregisterCommand(cls.cmd)

    @classmethod
    def create(cls):
        return cls()

    @classmethod
    def create_syntax(cls):
        return om.MSyntax()

    def __init__(self):
        super(Command, self).__init__()

        # Set this to true after an action that can be undone.
        self.undoable = False

    def args(self, args):
        """
        Parse arguments and return an MArgParser.

        If the arguments aren't valid, return None.  Maya will have printed an error, so
        we should just stop if that happens.
        """
        try:
            return om.MArgParser(self.syntax(), args)
        except RuntimeError:
            return None

    def isUndoable(self):
        return self.undoable

