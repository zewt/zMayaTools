import math, os, shutil, sys
import maya.OpenMayaMPx as OpenMayaMPx
import maya.OpenMaya as om
import maya.OpenMayaRender as omr
import pymel.core as pm
from pymel.tools import py2mel

from zMayaTools import maya_logging
log = maya_logging.get_log()

class zFileSwitch(OpenMayaMPx.MPxNode):
    pluginNodeId = om.MTypeId(0x12474D)

    def compute(self, plug, dataBlock):
        if plug == self.attr_output:
            use_override_idx = dataBlock.inputValue(self.attr_override).asShort()
            if use_override_idx == 0:
                # In "Off", use the Use High Res value.
                use_high_res = dataBlock.inputValue(self.attr_use_high_res).asBool()
            else:
                # We're forcing low or high res.
                use_high_res = use_override_idx == 2

            # Get the paths to try.  If use_high_res is true, reverse the order so we try
            # the high-res path first.
            low_res_path = dataBlock.inputValue(self.attr_low_res).asString()
            high_res_path = dataBlock.inputValue(self.attr_high_res).asString()
            paths = [low_res_path, high_res_path]
            if use_high_res:
                paths.reverse()

            for path in paths:
                # See if this path exists.  This will return "" if the file doesn't exist, or
                # an absolute path if it does.  Note that we're not actually going to pass the
                # resolved filename as the output, we're just doing this to check if the file
                # exists.
                exact_name = omr.MRenderUtil.exactFileTextureName(path, False, "", self.name())
                if exact_name:
                    break
            else:
                # Neither file existed, so use the first choice.
                path = paths[0]

            output = dataBlock.outputValue(plug)
            output.setString(path)
            
            return

        return super(zFileSwitch, self).compute(plug, dataBlock)

    @classmethod
    def initialize(cls):
        nAttr = om.MFnNumericAttribute()
        matAttr = om.MFnMatrixAttribute()
        typedAttr = om.MFnTypedAttribute()
        cmpAttr = om.MFnCompoundAttribute()
        enumAttr = om.MFnEnumAttribute()

        cls.attr_output = typedAttr.create('output', 'out', om.MFnData.kString)
        typedAttr.setWritable(False)
        typedAttr.setStorable(False)
        cls.addAttribute(cls.attr_output)

        cls.attr_low_res = typedAttr.create('lowResolution', 'lr', om.MFnData.kString)
        cls.addAttribute(cls.attr_low_res)
        cls.attributeAffects(cls.attr_low_res, cls.attr_output)

        cls.attr_high_res = typedAttr.create('highResolution', 'hr', om.MFnData.kString)
        cls.addAttribute(cls.attr_high_res)
        cls.attributeAffects(cls.attr_high_res, cls.attr_output)

        cls.attr_use_high_res = nAttr.create('useHighRes', 'uhr', om.MFnNumericData.kBoolean, True)
        typedAttr.setChannelBox(True)
        cls.addAttribute(cls.attr_use_high_res)
        cls.attributeAffects(cls.attr_use_high_res, cls.attr_output)

        cls.attr_override = enumAttr.create('override', 'ovr')
        enumAttr.addField('Off', 0)
        enumAttr.addField('Force low-res', 1)
        enumAttr.addField('Force high-res', 2)
        enumAttr.setDefault('Off')
        cls.addAttribute(cls.attr_override)
        cls.attributeAffects(cls.attr_override, cls.attr_output)

    @classmethod
    def creator(cls):
        return OpenMayaMPx.asMPxPtr(zFileSwitch())

def copy_render_setup_template():
    """
    Copy our render setup template into the user template directory.

    This is annoying, but MAYA_RENDER_SETUP_GLOBAL_TEMPLATE_PATH doesn't
    accept a list of paths like MAYA_CUSTOM_TEMPLATE_PATH does, so we can't
    just add a directory to the search path.
    """
    # Work around a Python bug: __file__ isn't defined in scripts run with execfile.
    def get_script_path():
        from inspect import getsourcefile
        from os.path import abspath
        return abspath(getsourcefile(lambda: 0))

    # We could check if the file exists to avoid the copy, but the file is so
    # small it's not worth it, and this makes sure we sync it up if we make changes
    # to it in the future.
    script_path = get_script_path()
    input_path = os.path.dirname(script_path) + '/../data/zFileSwitch.json'
    rs_path = pm.optionVar(q='renderSetup_userTemplateDirectory')
    output_path = rs_path + '/zFileSwitch.json'
    shutil.copyfile(input_path, output_path)

def initializePlugin(mobject):
    plugin = OpenMayaMPx.MFnPlugin(mobject)
    plugin.registerNode('zFileSwitch', zFileSwitch.pluginNodeId, zFileSwitch.creator, zFileSwitch.initialize, OpenMayaMPx.MPxNode.kDependNode)

    copy_render_setup_template()

def uninitializePlugin(mobject):
    plugin = OpenMayaMPx.MFnPlugin(mobject)
    plugin.deregisterNode(zFileSwitch.pluginNodeId)

# AE:
from maya import OpenMaya as om
from pymel.tools import py2mel

def AEzFileSwitchTemplate(nodeName):
    pm.editorTemplate(beginScrollLayout=True)
    pm.editorTemplate(beginLayout='File Switch Attributes', collapse=False)

    # Unfortunately, these only work if they're strings of global MEL functions
    # and can't take a Python function like most APIs.
    pm.editorTemplate('AEzFileSwitchPathNew', 'AEzFileSwitchPathReplace', 'highResolution', callCustom=True)
    pm.editorTemplate('AEzFileSwitchPathNew', 'AEzFileSwitchPathReplace', 'lowResolution', callCustom=True)

    pm.editorTemplate('useHighRes', addControl=True)
    pm.editorTemplate('override', addControl=True)
    pm.editorTemplate('zFileSwitchRefreshNew', 'zFileSwitchRefreshReplace', 'output', callCustom=True)

    pm.editorTemplate(endLayout=True)
    pm.mel.eval('AEabstractBaseCreateTemplate %s' % nodeName)
    pm.editorTemplate(addExtraControls=True)
    pm.editorTemplate(endScrollLayout=True)
py2mel.py2melProc(AEzFileSwitchTemplate)

def AEzFileSwitchPathNew(fileAttribute):
    pm.setUITemplate('attributeEditorTemplate', pst=True)
    pm.columnLayout(adj=True)
    pm.rowLayout(nc=3)

    if fileAttribute.split('.')[-1] == 'highResolution':
        label = 'High-resolution'
    else:
        label = 'Low-resolution'

    pm.text('filenameName', label=label)
    pm.textField('filenameField', fileName='')
    pm.symbolButton('browseFileSwitch', image='navButtonBrowse.png')
    pm.setParent('..')
    pm.setParent('..')

    pm.setUITemplate(ppt=True)

    AEzFileSwitchPathReplace(fileAttribute)
py2mel.py2melProc(AEzFileSwitchPathNew)

def AEzFileSwitchPathReplace(fileAttribute):
    def open_file_browser(unused):
        old_path = pm.getAttr(fileAttribute)
        old_path = old_path.replace('\\', '/')
        starting_file = os.path.basename(old_path)

        # Find the absolute path to the current path, if any, and open the browser in the
        # same directory as the current path.  Why don't all Maya file browsers do this?
        starting_directory = ''
        if old_path:
            attr = pm.ls(fileAttribute)[0]
            node_name = attr.nodeName()
            absolute_path = omr.MRenderUtil.exactFileTextureName(old_path, False, "", node_name)
            starting_directory = os.path.dirname(absolute_path)

        options = pm.mel.eval('fileBrowserActionSetup("image", 1)')
        files = pm.fileDialog2(caption='Open', okCaption='Open', fileMode=1,
                fileFilter=options[2],
                startingDirectory=starting_directory,
                selectFileFilter=starting_file)
        if not files:
            return
        path = files[0]
        path = path.replace('\\', '/')

        pm.setAttr(fileAttribute, path)

    pm.connectControl('filenameField', fileAttribute, fileName=True)

    pm.textField('filenameField', e=True, changeCommand=lambda value: pm.setAttr(fileAttribute, value))
    pm.button('browseFileSwitch', e=True, command=open_file_browser)
    return True

py2mel.py2melProc(AEzFileSwitchPathReplace)

# The "Refresh" button.  This just dirties the output attribute, so it gets reevaluated.
def zFileSwitchRefreshNew(attr):
    # Is there a less dumb way to align the button sensibly?
    pm.rowLayout(nc=5, cl5=("center", "center", "center", "center", "center"))
    pm.text(label='')
    pm.button('refreshFileSwitch', label='Refresh')
    pm.text(label='')
    pm.text(label='')
    pm.text(label='')
    pm.setParent('..')
        
    zFileSwitchRefreshReplace(attr)

py2mel.py2melProc(zFileSwitchRefreshNew)

def zFileSwitchRefreshReplace(attr):
    def refresh(unused):
        # Dirty the .output attribute to force it to be reevaluated, so if a file exists
        # in a slot that didn't exist before, it'll find it.
        pm.system.dgdirty(attr)

        # Fire the textureReload callback to tell the viewport to reload the texture.
        path = pm.getAttr(attr)
        pm.callbacks(executeCallbacks=True, hook='textureReload %s' % path)
    pm.button('refreshFileSwitch', e=True, command=refresh)
py2mel.py2melProc(zFileSwitchRefreshReplace)

