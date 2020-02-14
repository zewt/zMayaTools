# This allows quickly assigning joint sides, incremental "other" joint
# labels, and a more logical ordering than the "Add Joint Labels" menu
# to make it easier to quickly find each joint.
#
# This is also much faster than labelling with a menu tearoff, since pick
# walking can be used to move from joint to joint (arrow keys with a tearoff
# menu will just navigate the menu).

import os, sys
import pymel.core as pm
import maya
from zMayaTools import maya_helpers, maya_logging, dockable_window, Qt, qt_helpers
from zMayaTools.dockable_window import DockableWindow
from zMayaTools.menus import Menu
try:
    from importlib import reload
except ImportError:
    pass

log = maya_logging.get_log()

# Joint label indices for each button.
joint_label_name_to_idx = {
    # Renamed from "None" or QT will throw an error.
    "NoLabel": 0,

    "Head": 8,
    "Neck": 7,
    "Spine": 6,
    "Hip": 2,
    "Root": 1,

    "Collar": 9,
    "Shoulder": 10,
    "Elbow": 11,
    "Hand": 12,

    "Knee": 3,
    "Foot": 4,
    "Toe": 5,

    "Finger": 13,
    "Index": 19,
    "Middle": 20,
    "Ring": 21,
    "Pinky": 22,
    "Thumb": 14,
    "ExtraFinger": 23,

    "BigToe": 24,
    "IndexToe": 25,
    "MiddleToe": 26,
    "RingToe": 27,
    "PinkyToe": 28,
    "ExtraToe": 29, # aka "Foot thumb"?

    "PropA": 15,
    "PropB": 16,
    "PropC": 17,

    "Other": 18,
}

class JointLabellingWindow(dockable_window.DockableWindow):
    def __init__(self):
        super(JointLabellingWindow, self).__init__()

        from zMayaTools.qt_generated import zJointLabelling
        reload(zJointLabelling)

        self.ui = zJointLabelling.Ui_zJointLabelling()
        self.ui.setupUi(self)

        self.ui.otherTextSet.clicked.connect(self.clicked_other_text_set)
        self.ui.otherTextEntry.returnPressed.connect(self.clicked_other_text_set)

        # Hook up to each of the joint label buttons.
        def connect_to_joint_button(joint_label_idx, label):
            def clicked():
                self.clicked_joint_button(joint_label_idx)

            button = getattr(self.ui, label)
            button.clicked.connect(clicked)

        for label, joint_label_idx in joint_label_name_to_idx.items():
            if label == 'Other':
                continue

            connect_to_joint_button(joint_label_idx, label)

        self.ui.centerSide.clicked.connect(lambda: self.clicked_joint_side(0))
        self.ui.leftSide.clicked.connect(lambda: self.clicked_joint_side(1))
        self.ui.rightSide.clicked.connect(lambda: self.clicked_joint_side(2))
        self.ui.noSide.clicked.connect(lambda: self.clicked_joint_side(3))
        self.ui.guessSide.clicked.connect(self.clicked_guess_joint_side)

    def clicked_other_text_set(self):
        label = self.ui.otherTextEntry.text()
        self.set_other(label)

    def set_other(self, label):
        selection = pm.ls(sl=True, type='joint')
        for idx, joint in enumerate(selection):
            # If the label contains #, replace it with the index, starting at 1.
            joint_label = label
            if '#' in label:
                joint_label = joint_label.replace('#', str(idx+1))
            joint.attr('type').set(joint_label_name_to_idx['Other'])
            joint.otherType.set(joint_label)

    def clicked_joint_button(self, idx):
        for joint in pm.ls(sl=True, type='joint'):
            joint.attr('type').set(idx)

    def clicked_joint_side(self, side_idx):
        for joint in pm.ls(sl=True, type='joint'):
            joint.side.set(side_idx)

    def clicked_guess_joint_side(self):
        # Set the side of a joint based on its X position.
        #
        # This is a quick way to set the side of joints.  A good policy is
        # to label joints on the YZ plane as center joints, joints with mirrored
        # left and right counterparts as left and right, and joints that aren't
        # in the center but which aren't mirrored as having no side.  This
        # doesn't do any mirror matching and just looks at the X position.
        for joint in pm.ls(sl=True, type='joint'):
            pos = pm.xform(joint, q=True, ws=True, t=True)
            side = 2 if pos[0] < -0.1 else 1 if pos[0] > 0.1 else 0
            joint.side.set(side)

class PluginMenu(Menu):
    def __init__(self):
        super(PluginMenu, self).__init__()
        self.window = maya_helpers.RestorableWindow(JointLabellingWindow, plugins='zMayaUtils.py',
            module='zMayaTools.joint_labelling', obj='menu.window')

    def _add_menu_items(self):
        super(PluginMenu, self)._add_menu_items()

        menu = 'MayaWindow|mainRigSkeletonsMenu'

        # Make sure the menu is built.
        pm.mel.eval('ChaSkeletonsMenu "%s";' % menu)

        self.add_menu_item('zMayaTools_JointLabelling', label='Joint Labelling', parent=menu, insertAfter='hikWindowItem',
                command=lambda unused: self.window.show(),
                image='smoothSkin.png',
                top_level_path='Rigging|Joint_Labelling')

    def _remove_menu_items(self):
        super(PluginMenu, self)._remove_menu_items()
        
        # If the window is open when the module is unloaded, close it.
        self.window.close()

menu = PluginMenu()

