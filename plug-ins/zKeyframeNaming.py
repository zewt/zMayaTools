from pymel import core as pm
import sys
import maya.OpenMayaMPx as OpenMayaMPx
import maya.OpenMaya as om
import math, traceback, time
from zMayaTools.menus import Menu

from zMayaTools import keyframe_naming
reload(keyframe_naming)

class zKeyframeNaming(OpenMayaMPx.MPxNode):
    pluginNodeId = keyframe_naming.plugin_node_id

    def compute(self, plug, dataBlock):
        if plug.isElement():
            plug = plug.array()

        if plug == self.attr_arnold_attribute_out:
            name_idx = dataBlock.inputValue(self.attr_keyframes).asInt()
            names = dataBlock.inputArrayValue(self.attr_names)
            try:
                names.jumpToElement(name_idx)
            except RuntimeError: # No element at given index
                name = 'unnamed'
            else:
                name = names.inputValue().asString()

            output = dataBlock.outputValue(plug)
            output.setString("STRING frameName %s" % name)
            
            return

        return super(zKeyframeNaming, self).compute(plug, dataBlock)

    @classmethod
    def initialize(cls):
        nAttr = om.MFnNumericAttribute()
        typedAttr = om.MFnTypedAttribute()

        cls.attr_arnold_attribute_out = typedAttr.create('arnoldAttributeOut', 'aao', om.MFnData.kString)
        typedAttr.setWritable(False)
        typedAttr.setStorable(False)
        typedAttr.setChannelBox(True)
        cls.addAttribute(cls.attr_arnold_attribute_out)

        cls.attr_keyframes = nAttr.create('keyframes', 'keys', om.MFnNumericData.kInt, 0)
        nAttr.setKeyable(True)
        cls.addAttribute(cls.attr_keyframes)
        cls.attributeAffects(cls.attr_keyframes, cls.attr_arnold_attribute_out)

        cls.attr_names = typedAttr.create('names', 'nms', om.MFnData.kString)
        typedAttr.setArray(True)
        cls.addAttribute(cls.attr_names)
        cls.attributeAffects(cls.attr_names, cls.attr_arnold_attribute_out)

    @classmethod
    def creator(cls):
        return OpenMayaMPx.asMPxPtr(zKeyframeNaming())

class PluginMenu(Menu):
    def __init__(self):
        super(PluginMenu, self).__init__()
        self.ui = None

    def add_menu_items(self):
        menu = 'MayaWindow|mainKeysMenu'

        # Make sure the menu is built.
        pm.mel.eval('AniKeyMenu "%s";' % menu)

        def show_window(unused):
            reload(keyframe_naming)
            if self.ui is None:
                self.ui = keyframe_naming.KeyframeNamingWindow()
                def closed():
                    self.ui = None
                self.ui.destroyed.connect(closed)

            # Disable retain, or we won't be able to create the window again after reloading the script
            # with an "Object's name 'DialogWorkspaceControl' is not unique" error.
            self.ui.show(dockable=True, retain=False)

        menu_items = pm.menu(menu, q=True, ia=True)
        section = self.find_menu_section_by_name(menu_items, 'Edit')
        self.add_menu_item('zMayaTools_zKeyframeNaming', label='Named Keyframes', parent=menu, insertAfter=section[-1],
                command=show_window)

    def remove_menu_items(self):
        super(PluginMenu, self).remove_menu_items()

        if self.ui is None:
            return

        # If the keying window is open when the module is unloaded, close it.
        self.ui.close()
        self.ui = None

menu = PluginMenu()
def initializePlugin(mobject):
    plugin = OpenMayaMPx.MFnPlugin(mobject)
    plugin.registerNode('zKeyframeNaming', zKeyframeNaming.pluginNodeId, zKeyframeNaming.creator, zKeyframeNaming.initialize, OpenMayaMPx.MPxNode.kDependNode)

    menu.add_menu_items()

def uninitializePlugin(mobject):
    plugin = OpenMayaMPx.MFnPlugin(mobject)
    plugin.deregisterNode(zKeyframeNaming.pluginNodeId)

    menu.remove_menu_items()

