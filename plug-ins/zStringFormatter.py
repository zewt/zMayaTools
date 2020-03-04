import math, sys
import maya.OpenMayaMPx as OpenMayaMPx
import maya.OpenMaya as om
import pymel.core as pm

from zMayaTools import maya_logging
log = maya_logging.get_log()

# This is experimental: a way to generically format string attributes using Python
# string formatting.
#
# It can be used in place of zArnoldMetadata, though formatting matrix attributes
# would be a pain.
#
# The interface for this is pretty ugly, with a separate array for each data type.
# Generic attributes (MFnGenericAttribute) might be a way of doing it better, but
# there's no way to query the actual type of a generic attribute, so we'd need
# to be able to figure it out from the format string.
class zStringFormatter(OpenMayaMPx.MPxNode):
    pluginNodeId = om.MTypeId(0x12474C)

    def compute(self, plug, dataBlock):
        if plug.isElement():
            plug = plug.array()

        if plug == self.attr_output:
            attrs = {}

            for type_name in 'inputIntEntries', 'inputFloatEntries', 'inputStringEntries':
                entries_attr = self.input_attr_entries[type_name]
                type_attr = self.input_attr_values[type_name]
                name_attr = self.input_attr_names[type_name]

                entries = dataBlock.inputArrayValue(entries_attr)
                for i in range(entries.elementCount()):
                    entries.jumpToArrayElement(i)
                    name = entries.inputValue().child(name_attr).asString()
                    value_attr = entries.inputValue().child(type_attr)
                    if type_attr is self.attr_int_value:
                        value = value_attr.asInt()
                    elif type_attr is self.attr_float_value:
                        value = value_attr.asFloat()
                    elif type_attr is self.attr_string_value:
                        value = value_attr.asString()
                    else:
                        raise RuntimeError('Unknown attribute type: %s' % type_attr)
                        
                    attrs[name] = value

            fmt = dataBlock.inputValue(self.attr_format).asString()

            output = dataBlock.outputValue(plug)
            try:
                formatted_value = fmt % attrs
            except ValueError as e:
                log.info('Invalid format string for %s: %s', self.name(), str(e))
                formatted_value = ''
            except KeyError as e:
                log.info('%s format uses unspecified key "%s": "%s"', self.name(), e.args[0], fmt)
                formatted_value = ''

            output.setString(formatted_value)
            
            return

        return super(zStringFormatter, self).compute(plug, dataBlock)

    @classmethod
    def initialize(cls):
        nAttr = om.MFnNumericAttribute()
        matAttr = om.MFnMatrixAttribute()
        typedAttr = om.MFnTypedAttribute()
        cmpAttr = om.MFnCompoundAttribute()

        cls.attr_output = typedAttr.create('output', 'out', om.MFnData.kString)
        typedAttr.setWritable(False)
        typedAttr.setStorable(False)
        typedAttr.setChannelBox(True)
        cls.addAttribute(cls.attr_output)

        # The name affects all outputs.
        cls.attr_format = typedAttr.create('format', 'fmt', om.MFnData.kString)
        cls.addAttribute(cls.attr_format)
        cls.attributeAffects(cls.attr_format, cls.attr_output)

        # Create input values for each data type.
        cls.input_attr_names = {}
        cls.input_attr_values = {}
        cls.input_attr_entries = {}
        def create_list_attr(value_attr, entries_attr_name, entries_attr_short, name_attr, name_attr_short):
            cls.addAttribute(value_attr)
            cls.attributeAffects(value_attr, cls.attr_output)

            name_attr = typedAttr.create(name_attr, entries_attr_short, om.MFnData.kString)
            cls.addAttribute(name_attr)
            cls.attributeAffects(name_attr, cls.attr_output)

            entries_attr = cmpAttr.create(entries_attr_name, name_attr_short)
            cmpAttr.addChild(name_attr)
            cmpAttr.addChild(value_attr)
            cmpAttr.setArray(True)
            cls.addAttribute(entries_attr)
            cls.attributeAffects(entries_attr, cls.attr_output)

            cls.input_attr_names[entries_attr_name] = name_attr
            cls.input_attr_values[entries_attr_name] = value_attr
            cls.input_attr_entries[entries_attr_name] = entries_attr

        cls.attr_int_value = nAttr.create('inputIntValue', 'iiv', om.MFnNumericData.kInt, 0)
        nAttr.setKeyable(True)
        create_list_attr(cls.attr_int_value, 'inputIntEntries', 'iin', 'inputIntName', 'ien')

        cls.attr_float_value = nAttr.create('inputFloatValue', 'ifv', om.MFnNumericData.kFloat, 0)
        nAttr.setKeyable(True)
        create_list_attr(cls.attr_float_value, 'inputFloatEntries', 'ife', 'inputFloatName', 'ifn')

        cls.attr_string_value = typedAttr.create('inputStringValue', 'isv', om.MFnData.kString)
        typedAttr.setKeyable(True)
        create_list_attr(cls.attr_string_value, 'inputStringEntries', 'ise', 'inputStringName', 'isn')

    @classmethod
    def creator(cls):
        return OpenMayaMPx.asMPxPtr(zStringFormatter())

def initializePlugin(mobject):
    plugin = OpenMayaMPx.MFnPlugin(mobject)
    plugin.registerNode('zStringFormatter', zStringFormatter.pluginNodeId, zStringFormatter.creator, zStringFormatter.initialize, OpenMayaMPx.MPxNode.kDependNode)

def uninitializePlugin(mobject):
    plugin = OpenMayaMPx.MFnPlugin(mobject)
    plugin.deregisterNode(zStringFormatter.pluginNodeId)

