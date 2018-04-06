import sys, logging
import maya.OpenMayaMPx as OpenMayaMPx
import maya.OpenMaya as om
import pymel.core
import math, traceback, time

from zMayaTools.rbf import rbf

from zMayaTools import maya_logging
log = maya_logging.get_log()

def iterate_array_handle(array):
    """
    Mostly fix MArrayDataHandle array iteration.
    """
    while True:
        # Call elementIndex() to see if there are any values at all.  It'll throw RuntimeError
        # if there aren't.
        try:
            array.elementIndex()
        except RuntimeError as e:
            # We've advanced beyond the end of the array.
            break

        yield array.inputValue()

        try:
            array.next()
        except RuntimeError as e:
            break

class zRBF(OpenMayaMPx.MPxNode):
    pluginNodeId = om.MTypeId(0x124744)

    def __init__(self, *args, **kwargs):
        super(zRBF, self).__init__(*args, **kwargs)
        self.rbf = None

    def compute(self, plug, data_block):
        if plug == self.attr_update:
            self.rbf = None

            samples = []
            outputs = []
            values = data_block.inputArrayValue(self.attr_value)
            for idx in xrange(values.elementCount()):
                values.jumpToArrayElement(idx)
                handle = values.inputValue()
                value_input = handle.child(zRBF.attr_value_Position)

                value_output = handle.child(zRBF.attr_value_Value)
                samples.append(value_input.asFloat3())
                outputs.append(value_output.asDouble())

            self.rbf = rbf.rbf(outputs, samples)
            return

        if plug == self.attr_solvable:
            data_block.inputValue(self.attr_update)

            output_handle = data_block.outputValue(self.attr_solvable)
            output_handle.setBool(self.rbf.solvable)
            return

        if plug == self.attr_outValue or plug == self.attr_outputAngleValue:
            # Touch updateAttr to update self.rbf.
            data_block.inputValue(self.attr_update)

            if plug.isArray():
                return om.kUnknownParameter

            idx = plug.logicalIndex()

            # Use outputArrayValue here so we don't evaluate all of the inputs.
            input_attr_handle = data_block.outputArrayValue(self.inputAttr)
            try:
                input_attr_handle.jumpToElement(idx)
                input_value = input_attr_handle.inputValue().asFloat3()
            except RuntimeError as e:
                input_value = (0,0,0)

            result = self.rbf.eval(input_value)

            output_value_factor_handle = data_block.outputArrayValue(self.attr_outValueFactor)
            try:
                output_value_factor_handle.jumpToElement(idx)
                output_factor = output_value_factor_handle.inputValue().asDouble()
                result *= output_factor
            except RuntimeError as e:
                pass

            if plug == self.attr_outValue:
                output_array_handle = data_block.outputArrayValue(self.attr_outValue)
            else:
                output_array_handle = data_block.outputArrayValue(self.attr_outputAngleValue)

            builder = output_array_handle.builder()
            output_handle = builder.addElement(idx)
            output_handle.setDouble(result)
            output_handle.setClean()
            
            return

        return super(zRBF, self).compute(plug, data_block)

    @classmethod
    def initialize(cls):
        mAttr = om.MFnMatrixAttribute()
        tAttr = om.MFnTypedAttribute()
        nAttr = om.MFnNumericAttribute()
        cmpAttr = om.MFnCompoundAttribute()
        uAttr = om.MFnUnitAttribute()

        # This attribute is true if we're solvable.  If this is false, the input is invalid and
        # the output will always be zero.
        cls.attr_solvable = nAttr.create('solvable', 'solvable', om.MFnNumericData.kBoolean, 0)
        nAttr.setWritable(False)
        nAttr.setStorable(False)
        cls.addAttribute(cls.attr_solvable)

        cls.attr_outValue = nAttr.create('outValue', 'o', om.MFnNumericData.kDouble, 0)
        nAttr.setArray(True)
        nAttr.setWritable(False)
        nAttr.setStorable(False)
        nAttr.setUsesArrayDataBuilder(True)
        cls.addAttribute(cls.attr_outValue)

        # This outputs the same value as attr_outValue, but as an angle.  For angle values, this allows
        # avoiding extra unitConversion nodes.
        cls.attr_outputAngleValue = uAttr.create('outAngleValue', 'oa', om.MFnUnitAttribute.kAngle, 0)
        uAttr.setArray(True)
        uAttr.setStorable(False)
        uAttr.setWritable(False)
        uAttr.setUsesArrayDataBuilder(True)
        cls.addAttribute(cls.attr_outputAngleValue)

        # Each output value is multiplied by its corresponding value in this array.  This is
        # just a convenience to avoid needing a bunch of multiplyDivide nodes.
        cls.attr_outValueFactor = nAttr.create('outValueFactor', 'ovf', om.MFnNumericData.kDouble, 1)
        nAttr.setArray(True)
        cls.addAttribute(cls.attr_outValueFactor)
        cls.attributeAffects(cls.attr_outValueFactor, cls.attr_outValue)
        cls.attributeAffects(cls.attr_outValueFactor, cls.attr_outputAngleValue)

        cls.attr_update = nAttr.create('update', 'update', om.MFnNumericData.kBoolean)
        nAttr.setHidden(True)
        nAttr.setStorable(False)
        cls.addAttribute(cls.attr_update)
        cls.attributeAffects(cls.attr_update, cls.attr_outValue)
        cls.attributeAffects(cls.attr_update, cls.attr_outputAngleValue)

        cls.attr_value_Position = nAttr.createPoint('value_Position', 'vp')
        cls.addAttribute(cls.attr_value_Position)
        cls.attributeAffects(cls.attr_value_Position, cls.attr_outValue)
        cls.attributeAffects(cls.attr_value_Position, cls.attr_outputAngleValue)
        cls.attributeAffects(cls.attr_value_Position, cls.attr_update)
        cls.attributeAffects(cls.attr_value_Position, cls.attr_solvable)

        cls.attr_value_Value = nAttr.create('value_Value', 'vv', om.MFnNumericData.kDouble)
        cls.addAttribute(cls.attr_value_Value)
        cls.attributeAffects(cls.attr_value_Value, cls.attr_outValue)
        cls.attributeAffects(cls.attr_value_Value, cls.attr_outputAngleValue)
        cls.attributeAffects(cls.attr_value_Value, cls.attr_update)
        cls.attributeAffects(cls.attr_value_Value, cls.attr_solvable)

        cls.attr_value = cmpAttr.create('value', 'v')
        cmpAttr.setArray(True)
        cmpAttr.addChild(cls.attr_value_Position)
        cmpAttr.addChild(cls.attr_value_Value)
        cls.addAttribute(cls.attr_value)
        cls.attributeAffects(cls.attr_value, cls.attr_outValue)
        cls.attributeAffects(cls.attr_value, cls.attr_outputAngleValue)
        cls.attributeAffects(cls.attr_value, cls.attr_update)
        cls.attributeAffects(cls.attr_value, cls.attr_solvable)

        cls.inputAttr = nAttr.createPoint('inputValue', 'i')
        nAttr.setArray(True)
        cls.addAttribute(cls.inputAttr)
        cls.attributeAffects(cls.inputAttr, cls.attr_outValue)
        cls.attributeAffects(cls.inputAttr, cls.attr_outputAngleValue)

    @classmethod
    def creator(cls):
        return OpenMayaMPx.asMPxPtr(cls())

def initializePlugin(mobject):
    plugin = OpenMayaMPx.MFnPlugin(mobject)
    plugin.registerNode('zRBF', zRBF.pluginNodeId, zRBF.creator, zRBF.initialize, OpenMayaMPx.MPxNode.kDependNode)

def uninitializePlugin(mobject):
    plugin = OpenMayaMPx.MFnPlugin(mobject)
    plugin.deregisterNode(zRBF.pluginNodeId)

