import math, sys
import maya.OpenMayaMPx as OpenMayaMPx
import maya.OpenMaya as om
import pymel.core as pm
from zMayaTools.menus import Menu

class zArnoldMetadata(OpenMayaMPx.MPxNode):
    pluginNodeId = om.MTypeId(0x12474A)

    def compute(self, plug, dataBlock):
        if plug.isElement():
            plug = plug.array()

        if plug in (self.attr_output_int, self.attr_output_float, self.attr_output_vector2, self.attr_output_matrix):
            name = dataBlock.inputValue(self.attr_name).asString()

            # Make sure the name is valid.
            if not name:
                name = 'name_not_set'
            name = name.replace(' ', '_')

            output = dataBlock.outputValue(plug)

            if plug == self.attr_output_int:
                value = dataBlock.inputValue(self.attr_int).asInt()
                output.setString("INT %s %i" % (name, value))
            elif plug == self.attr_output_float:
                value = dataBlock.inputValue(self.attr_float).asFloat()
                output.setString("FLOAT %s %f" % (name, value))
            elif plug == self.attr_output_vector2:
                value = dataBlock.inputValue(self.attr_vector2).asFloat2()
                output.setString("VECTOR2 %s %f %f" % (name, value[0], value[1]))
            elif plug == self.attr_output_matrix:
                value = dataBlock.inputValue(self.attr_matrix).asMatrix()
                vals = []
                for x in xrange(4):
                    for y in xrange(4):
                        vals.append('%f' % value(x,y))
                value = ' '.join(vals)
                output.setString("MATRIX %s %s" % (name, value))
            
            return

        return super(zArnoldMetadata, self).compute(plug, dataBlock)

    @classmethod
    def initialize(cls):
        nAttr = om.MFnNumericAttribute()
        matAttr = om.MFnMatrixAttribute()
        typedAttr = om.MFnTypedAttribute()

        # Add a separate output attribute for each data type.
        cls.attr_output_int = typedAttr.create('outputInt', 'oi', om.MFnData.kString)
        typedAttr.setWritable(False)
        typedAttr.setStorable(False)
        typedAttr.setChannelBox(True)
        cls.addAttribute(cls.attr_output_int)

        cls.attr_output_float = typedAttr.create('outputFloat', 'of', om.MFnData.kString)
        typedAttr.setWritable(False)
        typedAttr.setStorable(False)
        typedAttr.setChannelBox(True)
        cls.addAttribute(cls.attr_output_float)

        cls.attr_output_vector2 = typedAttr.create('outputVector2', 'ov2', om.MFnData.kString)
        typedAttr.setWritable(False)
        typedAttr.setStorable(False)
        typedAttr.setChannelBox(True)
        cls.addAttribute(cls.attr_output_vector2)

        cls.attr_output_matrix = typedAttr.create('outputMatrix', 'om', om.MFnData.kString)
        typedAttr.setWritable(False)
        typedAttr.setStorable(False)
        typedAttr.setChannelBox(True)
        cls.addAttribute(cls.attr_output_matrix)

        # The name affects all outputs.
        cls.attr_name = typedAttr.create('name', 'n', om.MFnData.kString)
        typedAttr.setChannelBox(True)
        cls.addAttribute(cls.attr_name)
        cls.attributeAffects(cls.attr_name, cls.attr_output_int)
        cls.attributeAffects(cls.attr_name, cls.attr_output_float)
        cls.attributeAffects(cls.attr_name, cls.attr_output_vector2)
        cls.attributeAffects(cls.attr_name, cls.attr_output_matrix)

        # Create input values for each data type.
        cls.attr_int = nAttr.create('inputInt', 'ii', om.MFnNumericData.kInt, 0)
        nAttr.setKeyable(True)
        cls.addAttribute(cls.attr_int)
        cls.attributeAffects(cls.attr_int, cls.attr_output_int)

        cls.attr_float = nAttr.create('inputFloat', 'if', om.MFnNumericData.kFloat, 0)
        nAttr.setKeyable(True)
        cls.addAttribute(cls.attr_float)
        cls.attributeAffects(cls.attr_float, cls.attr_output_float)

        inputVector2XAttr = nAttr.create('inputVector2X', 'ivx', om.MFnNumericData.kFloat, 0.0)
        inputVector2YAttr = nAttr.create('inputVector2Y', 'ivy', om.MFnNumericData.kFloat, 0.0)
        cls.attr_vector2 = nAttr.create('inputVector2', 'iv', inputVector2XAttr, inputVector2YAttr)
        nAttr.setKeyable(True)
        cls.addAttribute(cls.attr_vector2)

        cls.attr_matrix = matAttr.create('inputMatrix', 'im', om.MFnMatrixAttribute.kDouble)
        nAttr.setKeyable(True)
        cls.addAttribute(cls.attr_matrix)
        cls.attributeAffects(cls.attr_matrix, cls.attr_output_matrix)

    @classmethod
    def creator(cls):
        return OpenMayaMPx.asMPxPtr(zArnoldMetadata())

def initializePlugin(mobject):
    plugin = OpenMayaMPx.MFnPlugin(mobject)
    plugin.registerNode('zArnoldMetadata', zArnoldMetadata.pluginNodeId, zArnoldMetadata.creator, zArnoldMetadata.initialize, OpenMayaMPx.MPxNode.kDependNode)

def uninitializePlugin(mobject):
    plugin = OpenMayaMPx.MFnPlugin(mobject)
    plugin.deregisterNode(zArnoldMetadata.pluginNodeId)

