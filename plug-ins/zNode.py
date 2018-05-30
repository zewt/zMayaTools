import maya.OpenMayaMPx as OpenMayaMPx
import maya.OpenMaya as om

from zMayaTools import maya_logging

# This is an empty DG node that does nothing.  It can be used as a holder node
# for custom data.
log = maya_logging.get_log()

class zNode(OpenMayaMPx.MPxNode):
    pluginNodeId = om.MTypeId(0x124754)

def creator():
    return OpenMayaMPx.asMPxPtr(zNode())

def initialize():
    pass

def initializePlugin(mobject):
    plugin = OpenMayaMPx.MFnPlugin(mobject)
    plugin.registerNode('zNode', zNode.pluginNodeId, creator, initialize, OpenMayaMPx.MPxNode.kDependNode)

def uninitializePlugin(mobject):
    plugin = OpenMayaMPx.MFnPlugin(mobject)
    plugin.deregisterNode(zNode.pluginNodeId)

