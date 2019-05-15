import pymel.core as pm
from zMayaTools import maya_helpers

# There are two toggles for "wireframe on shaded": one in preferences, with "full", "reduced"
# (legacy?) and "none", and one for each viewport in the "Shading" menu.
# 
# To turn on wireframes for the selected object, and no wireframes for anything else,
# the global preference needs to be on "full", and the viewport's setting turned off.
# 
# To turn on wireframes for all objects, the global preference needs to be "full" and
# the viewport's setting turned on.
# 
# To turn off all wireframe on shaded, set the global preference to "none".
# 
# These features are inconsistently with each other: part of the setting is global
# and part is per viewport, so we don't try to do this per viewport and just set it
# on all viewports.  If you don't want wireframes on a particular viewport, turn
# off Show > Selection Highlighting on that viewport.
def get_wireframe_mode():
    if pm.displayPref(q=True, wireframeOnShadedActive=True) == 'none':
        return 'none'

    # Look at an arbitrary viewport for the wireframeOnShaded viewport mode.
    model_panels = pm.getPanel(type='modelPanel')
    if not model_panels:
        return 'none'
    if pm.modelEditor(model_panels[0], q=True, wireframeOnShaded=True):
        return 'all'
    else:
        return 'selected'
        
def set_wireframe_mode(mode):
    """
    Select a viewport wireframe mode:

    "none": no wireframes
    "selected": wireframes on selected objects
    "all": wireframes on all objects
    """
    assert mode in ('none', 'selected', 'all'), mode
    
    if mode == 'none':
        pm.displayPref(wireframeOnShadedActive='none')
    else:
        pm.displayPref(wireframeOnShadedActive='full')
        for model_panel in pm.getPanel(type='modelPanel'):
            enabled = mode == 'all'
            pm.modelEditor(model_panel, e=True, wireframeOnShaded=enabled)

def toggle_wireframe_on_selected():
    """
    Toggle wireframe on selected.
    
    If we're currently in "wireframe everything" mode, switch to wireframe on selected.
    """
    set_wireframe_mode('selected' if get_wireframe_mode() != 'selected' else 'none')

def toggle_wireframe_all():            
    """
    Toggle wireframe on everything.
    
    If we're currently in "wireframe selected" mode, switch to wireframing everything.
    """
    set_wireframe_mode('all' if get_wireframe_mode() != 'all' else 'none')

def setup_runtime_commands():
    maya_helpers.create_or_replace_runtime_command('zToggleWireframeSelected', category='zMayaTools.Viewport',
            command='from zMayaTools import wireframes; wireframes.toggle_wireframe_on_selected()',
            annotation='Toggle wireframe on selected')
    maya_helpers.create_or_replace_runtime_command('zToggleWireframeAll', category='zMayaTools.Viewport', 
            command='from zMayaTools import wireframes; wireframes.toggle_wireframe_all()',
            annotation='Toggle wireframe on all')

