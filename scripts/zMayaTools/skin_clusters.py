import pymel.core as pm
import maya.cmds as cmds
from maya import OpenMaya as om
from zMayaTools import maya_helpers, command

from zMayaTools import maya_logging
log = maya_logging.get_log()

# There's no way to query if moveJointsMode is enabled, so we have to track it ourselves.
move_skinned_joints_enabled = False

class MoveSkinnedJoints(command.Command):
    cmd = 'zMoveSkinnedJoints'

    @classmethod
    def create_syntax(cls):
        syntax = om.MSyntax()
        syntax.enableQuery(True)
        syntax.addFlag('-en', '-enable', om.MSyntax.kBoolean)
        syntax.addFlag('-t', '-toggle')
        return syntax

    def __init__(self):
        super(MoveSkinnedJoints, self).__init__()
        self.previous_state = move_skinned_joints_enabled

    def doIt(self, args):
        self.data = self.args(args)
        if self.data is None:
            return

        self.redoIt()

    def redoIt(self):
        if self.data.isFlagSet('-toggle'):
            self.set_enabled(not move_skinned_joints_enabled)
        elif self.data.isFlagSet('-enable'):
            if self.data.isQuery():
                self.setResult(move_skinned_joints_enabled)
                return

            enable = self.data.flagArgumentBool('-enable', 0)
            self.set_enabled(enable)

    def undoIt(self):
        with maya_helpers.without_undo():
            self.set_enabled(self.previous_state)

    def set_enabled(self, value):
        global move_skinned_joints_enabled
        move_skinned_joints_enabled = value

        # Disable undo while we do this, so these commands don't create their own
        # undo chunk, which causes redoing to clear the redo queue.  This is safe
        # since we'll explicitly handle undo in undoIt.
        with maya_helpers.without_undo():
            # Note that there's no query for moveJointsMode.
            nodes = pm.ls(type='skinCluster')
            for node in nodes:
                pm.skinCluster(node, e=True, moveJointsMode=value)

        if value:
            pm.inViewMessage(statusMessage='Move skinned joints mode active', pos='botCenter')
        else:
            pm.inViewMessage(clear='botCenter')

        self.undoable = True

