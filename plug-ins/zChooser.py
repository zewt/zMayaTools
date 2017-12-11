import sys
import maya.OpenMayaMPx as OpenMayaMPx
import maya.OpenMaya as om
import math, traceback, time

class zChooser(OpenMayaMPx.MPxNode):
    pluginNodeId = om.MTypeId(0x124748)

    def compute(self, plug, dataBlock):
        if plug.isElement():
            plug = plug.array()

        if plug == self.attr_output:
            true_value = dataBlock.inputValue(self.attr_selectedValue).asDouble()
            false_value = dataBlock.inputValue(self.attr_unselectedValue).asDouble()
            choice = dataBlock.inputValue(self.attr_Choice).asInt()

            output_array_handle = dataBlock.outputArrayValue(self.attr_output)

            ids = om.MIntArray()
            plug.getExistingArrayAttributeIndices(ids)
            builder = output_array_handle.builder()
            for idx in ids:
                outputHandle = builder.addElement(idx)
                outputHandle.setDouble(true_value if idx == choice else false_value)
            output_array_handle.set(builder)
            
            return

        return super(zChooser, self).compute(plug, dataBlock)

    @classmethod
    def initialize(cls):
        nAttr = om.MFnNumericAttribute()

        cls.attr_output = nAttr.create('output', 'o', om.MFnNumericData.kDouble, 0)
        nAttr.setWritable(False)
        nAttr.setArray(True)
        nAttr.setStorable(False)
        nAttr.setUsesArrayDataBuilder(True)
        nAttr.setChannelBox(True)
        cls.addAttribute(cls.attr_output)

        cls.attr_selectedValue = nAttr.create('selectedValue', 'sv', om.MFnNumericData.kDouble, 1)
        nAttr.setKeyable(True)
        nAttr.setReadable(False)
        cls.addAttribute(cls.attr_selectedValue)
        cls.attributeAffects(cls.attr_selectedValue, cls.attr_output)

        cls.attr_unselectedValue = nAttr.create('unselectedValue', 'usv', om.MFnNumericData.kDouble, 0)
        nAttr.setKeyable(True)
        nAttr.setReadable(False)
        cls.addAttribute(cls.attr_unselectedValue)
        cls.attributeAffects(cls.attr_unselectedValue, cls.attr_output)

        cls.attr_Choice = nAttr.create('choice', 'ch', om.MFnNumericData.kInt, 0)
        nAttr.setKeyable(True)
        nAttr.setReadable(False)
        cls.addAttribute(cls.attr_Choice)
        cls.attributeAffects(cls.attr_Choice, cls.attr_output)

    @classmethod
    def creator(cls):
        return OpenMayaMPx.asMPxPtr(zChooser())

def initializePlugin(mobject):
    plugin = OpenMayaMPx.MFnPlugin(mobject)
    plugin.registerNode('zChooser', zChooser.pluginNodeId, zChooser.creator, zChooser.initialize, OpenMayaMPx.MPxNode.kDependNode)

def uninitializePlugin(mobject):
    plugin = OpenMayaMPx.MFnPlugin(mobject)
    plugin.deregisterNode(zChooser.pluginNodeId)

