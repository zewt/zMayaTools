import sys
from pymel import core as pm
import maya.OpenMayaMPx as OpenMayaMPx
import maya.OpenMaya as om
import math, traceback, time
from zMayaTools import mouth_keying

class zMouthController(OpenMayaMPx.MPxNode):
    def postConstructor(self):
        self.setExistWithoutInConnections(True)
        self.setExistWithoutOutConnections(True)
    
    def compute(self, plug, dataBlock):
        if plug.isElement():
            plug = plug.array()

        if plug == self.outValueAttr:
            selection = dataBlock.inputValue(self.selectionAttr).asDouble()
            choice1 = dataBlock.inputValue(self.choice1Attr).asInt()
            choice2 = dataBlock.inputValue(self.choice2Attr).asInt()

            mainWeight = dataBlock.inputValue(self.mainWeightAttr).asDouble()

            solo = dataBlock.inputValue(self.soloAttr).asInt()
            if solo == 1:
                selection = 0
            elif solo == 2:
                selection = 1
            if solo != 0:
                mainWeight = 1

            inputWeight1 = dataBlock.inputValue(self.weight1Attr).asDouble() * mainWeight
            inputWeight2 = dataBlock.inputValue(self.weight2Attr).asDouble() * mainWeight

            weight1 = max(0, min(1, 1 - abs(    selection))) * inputWeight1
            weight2 = max(0, min(1, 1 - abs(1 - selection))) * inputWeight2

            if choice1 == choice2:
                weight1 += weight2
                choice2 = None

            # print '%f %f %f %f %s' % (weight, weight1, weight2, choice1, choice2)

            outputArrayHandle = dataBlock.outputArrayValue(self.outValueAttr)

            ids = om.MIntArray()
            plug.getExistingArrayAttributeIndices(ids)
            builder = outputArrayHandle.builder()
            for idx in ids:
                outputHandle = builder.addElement(idx)
                if idx == choice1:
                    value = weight1
                elif idx == choice2:
                    value = weight2
                else:
                    value = 0
                outputHandle.setDouble(value)
            outputArrayHandle.set(builder)
            
            return

        return super(zMouthController, self).compute(plug, dataBlock)

    @classmethod
    def initialize(cls):
        nAttr = om.MFnNumericAttribute()

        cls.outValueAttr = nAttr.create('output', 'o', om.MFnNumericData.kDouble, 0)
        nAttr.setWritable(False)
        nAttr.setArray(True)
        nAttr.setStorable(False)
        nAttr.setUsesArrayDataBuilder(True)
        nAttr.setChannelBox(True)
        cls.addAttribute(cls.outValueAttr)

        cls.selectionAttr = nAttr.create('selection', 'sel', om.MFnNumericData.kDouble, 0)
        nAttr.setKeyable(True)
        nAttr.setMin(0)
        nAttr.setMax(1)
        cls.addAttribute(cls.selectionAttr)
        cls.attributeAffects(cls.selectionAttr, cls.outValueAttr)

        cls.choice1Attr = nAttr.create('choice1', 'ch1', om.MFnNumericData.kInt, 0)
        nAttr.setKeyable(True)
        cls.addAttribute(cls.choice1Attr)
        cls.attributeAffects(cls.choice1Attr, cls.outValueAttr)

        cls.choice2Attr = nAttr.create('choice2', 'ch2', om.MFnNumericData.kInt, 0)
        nAttr.setKeyable(True)
        cls.addAttribute(cls.choice2Attr)
        cls.attributeAffects(cls.choice2Attr, cls.outValueAttr)

        # weight1 and weight2 are multiplied by mainWeight, to act as a top-level weight control.
        cls.mainWeightAttr = nAttr.create('mainWeight', 'mw', om.MFnNumericData.kDouble, 0)
        nAttr.setKeyable(True)
        cls.addAttribute(cls.mainWeightAttr)
        cls.attributeAffects(cls.mainWeightAttr, cls.outValueAttr)

        # If choice1 is used, its output can be at most weight1.
        cls.weight1Attr = nAttr.create('weight1', 'w1', om.MFnNumericData.kDouble, 1)
        nAttr.setKeyable(True)
        cls.addAttribute(cls.weight1Attr)
        cls.attributeAffects(cls.weight1Attr, cls.outValueAttr)

        # If choice2 is used, its output can be at most weight2.
        cls.weight2Attr = nAttr.create('weight2', 'w2', om.MFnNumericData.kDouble, 1)
        nAttr.setKeyable(True)
        cls.addAttribute(cls.weight2Attr)
        cls.attributeAffects(cls.weight2Attr, cls.outValueAttr)

        # When solo is set to 1 or 2, we'll ignore .selection and act as if it's set
        # to 0 or 1.  This is used for soloing in the UI.
        cls.soloAttr = nAttr.create('solo', 'so', om.MFnNumericData.kInt, 0)
        nAttr.setMin(0)
        nAttr.setMax(2)
        cls.addAttribute(cls.soloAttr)
        cls.attributeAffects(cls.soloAttr, cls.outValueAttr)

    @classmethod
    def creator(cls):
        return OpenMayaMPx.asMPxPtr(zMouthController())

def initializePlugin(mobject):
    plugin = OpenMayaMPx.MFnPlugin(mobject)
    plugin.registerNode('zMouthController', mouth_keying.plugin_node_id, zMouthController.creator, zMouthController.initialize, OpenMayaMPx.MPxNode.kDependNode)

    mouth_keying.menu.add_menu_items()

def uninitializePlugin(mobject):
    plugin = OpenMayaMPx.MFnPlugin(mobject)
    plugin.deregisterNode(mouth_keying.plugin_node_id)

    mouth_keying.menu.remove_menu_items()

