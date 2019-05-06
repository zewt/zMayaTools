from zMayaTools import maya_helpers
from pymel import core as pm

def pick_walk_add(direction):
    """
    Pick walk in a direction, adding the picked nodes to the selection instead of
    replacing the selection.
    """
    # pm.pickWalk is the basic pick walk command, but PickWalkUp, etc. have special
    # cases for certain types of selections.  These are four copied-and-pasted commands
    # instead of just one with an argument, so we need to map to the corresponding
    # command.
    assert direction in ('up', 'down', 'left', 'right')

    pick_walk_commands = {
        'up': 'PickWalkUp',
        'down': 'PickWalkDown',
        'left': 'PickWalkLeft',
        'right': 'PickWalkRight',
    }

    # Store the current selection.
    selection = pm.ls(sl=True)

    # Execute the pick walk.  This will replace the selection.
    pm.mel.eval(pick_walk_commands[direction])
    new_selection = pm.ls(sl=True)

    # Select the original selection, then add the new selection after it.
    pm.select(selection, ne=True)
    pm.select(new_selection, add=True)

def setup_runtime_commands():
    maya_helpers.create_or_replace_runtime_command('zPickWalkAddUp', category='zMayaTools.Miscellaneous',
            annotation='zMayaTools: Pick walk up, adding to the selection',
            command='from zMayaTools import pick_walk; pick_walk.pick_walk_add("up")')
    maya_helpers.create_or_replace_runtime_command('zPickWalkAddDown', category='zMayaTools.Miscellaneous',
            annotation='zMayaTools: Pick walk down, adding to the selection',
            command='from zMayaTools import pick_walk; pick_walk.pick_walk_add("down")')
    maya_helpers.create_or_replace_runtime_command('zPickWalkAddLeft', category='zMayaTools.Miscellaneous',
            annotation='zMayaTools: Pick walk left, adding to the selection',
            command='from zMayaTools import pick_walk; pick_walk.pick_walk_add("left")')
    maya_helpers.create_or_replace_runtime_command('zPickWalkAddRight', category='zMayaTools.Miscellaneous',
            annotation='zMayaTools: Pick walk right, adding to the selection',
            command='from zMayaTools import pick_walk; pick_walk.pick_walk_add("right")')

