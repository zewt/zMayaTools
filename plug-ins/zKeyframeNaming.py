from pymel import core as pm
import sys
import maya.OpenMayaMPx as OpenMayaMPx
import maya.OpenMaya as om
import math, traceback, time
from zMayaTools import maya_helpers

from zMayaTools import keyframe_naming
reload(keyframe_naming)

class zKeyframeNaming(OpenMayaMPx.MPxNode):
    pluginNodeId = keyframe_naming.plugin_node_id

    def postConstructor(self):
        self.setExistWithoutInConnections(True)
        self.setExistWithoutOutConnections(True)

    def compute(self, plug, dataBlock):
        if plug.isElement():
            plug = plug.array()

        if plug in (self.attr_current_keyframe_name_out, self.attr_arnold_attribute_out):
            key_idx = dataBlock.inputValue(self.attr_keyframes).asInt()
            entries = dataBlock.inputArrayValue(self.attr_entries)
            
            try:
                entries.jumpToElement(key_idx)
            except RuntimeError: # No element at given index
                name = 'unnamed'
            except OverflowError: # Out of range
                name = 'unnamed'
            else:
                name = entries.inputValue().child(self.attr_names).asString()

            output = dataBlock.outputValue(plug)
            if plug == self.attr_current_keyframe_name_out:
                output.setString(name)
            else:
                output.setString("STRING frameName %s" % name)
            
            return

        return super(zKeyframeNaming, self).compute(plug, dataBlock)

    @classmethod
    def initialize(cls):
        nAttr = om.MFnNumericAttribute()
        typedAttr = om.MFnTypedAttribute()
        cmpAttr = om.MFnCompoundAttribute()

        cls.attr_current_keyframe_name_out = typedAttr.create('currentKeyframeName', 'knn', om.MFnData.kString)
        typedAttr.setWritable(False)
        typedAttr.setStorable(False)
        typedAttr.setChannelBox(True)
        cls.addAttribute(cls.attr_current_keyframe_name_out)

        cls.attr_arnold_attribute_out = typedAttr.create('arnoldAttributeOut', 'aao', om.MFnData.kString)
        typedAttr.setWritable(False)
        typedAttr.setStorable(False)
        typedAttr.setChannelBox(True)
        cls.addAttribute(cls.attr_arnold_attribute_out)

        cls.attr_keyframes = nAttr.create('keyframes', 'keys', om.MFnNumericData.kInt, 0)
        nAttr.setKeyable(True)
        cls.addAttribute(cls.attr_keyframes)
        cls.attributeAffects(cls.attr_keyframes, cls.attr_arnold_attribute_out)
        cls.attributeAffects(cls.attr_keyframes, cls.attr_current_keyframe_name_out)

        cls.attr_names = typedAttr.create('name', 'nm', om.MFnData.kString)
        cls.addAttribute(cls.attr_names)
        cls.attributeAffects(cls.attr_names, cls.attr_arnold_attribute_out)
        cls.attributeAffects(cls.attr_names, cls.attr_current_keyframe_name_out)

        cls.attr_entries = cmpAttr.create('entries', 'en')
        cmpAttr.addChild(cls.attr_names)
        cmpAttr.setArray(True)
        cls.addAttribute(cls.attr_entries)
        cls.attributeAffects(cls.attr_entries, cls.attr_arnold_attribute_out)
        cls.attributeAffects(cls.attr_entries, cls.attr_current_keyframe_name_out)

    @classmethod
    def creator(cls):
        return OpenMayaMPx.asMPxPtr(zKeyframeNaming())

def initializePlugin(mobject):
    plugin = OpenMayaMPx.MFnPlugin(mobject)
    plugin.registerNode('zKeyframeNaming', zKeyframeNaming.pluginNodeId, zKeyframeNaming.creator, zKeyframeNaming.initialize, OpenMayaMPx.MPxNode.kDependNode)

    keyframe_naming.menu.add_menu_items()

def uninitializePlugin(mobject):
    plugin = OpenMayaMPx.MFnPlugin(mobject)
    plugin.deregisterNode(zKeyframeNaming.pluginNodeId)

    keyframe_naming.menu.remove_menu_items()

