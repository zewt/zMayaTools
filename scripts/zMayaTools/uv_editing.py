import pymel.core as pm
from maya import OpenMaya as om
import math

def set_symmetry_axis(components):
    """
    Given a list of components, set the UV symmetry mirror axis and axis position.

    If the components only have 1 UV, the axis position will be set based on the
    currently selected axis.
    """
    uvs = pm.polyEditUV(components, q=True)
    uvs = [(u, v) for u, v in zip(uvs[0::2], uvs[1::2])]
    
    # Find the bounding box of the selection.
    bounds_u = min(u for u, v in uvs), max(u for u, v in uvs)
    bounds_v = min(v for u, v in uvs), max(v for u, v in uvs)
    
    # Choose a vertical or horizontal axis based on the bounding box.
    width = abs(bounds_u[0] - bounds_u[1])
    height = abs(bounds_v[0] - bounds_v[1])
    
    # Do a quick sanity check to make sure the selection is vertical or horizontal.ww
    angle = math.atan2(width, height) * 180 / math.pi
    tol = 10
    if abs(angle) > tol and abs(90 - angle) > tol:
        om.MGlobal.displayInfo('Selected symmetry plane isn\'t axis-aligned')
        return
    
    if width == 0 and height == 0:
        # If the size is 0, a single UV was selected.  Just set the axis based on the current mode.
        u_axis = pm.optionVar(q='polySymmetrizeUVAxis')
    else:
        # If the bounding box is vertical, the seam is on the V plane.
        u_axis = width > height
        pm.optionVar(iv=('polySymmetrizeUVAxis', 1 if u_axis else 0))

    # Use the average of the selection as the mirror plane.  If there's only one UV selected, this will
    # be its position.    
    if u_axis:
        offset = (bounds_v[0] + bounds_v[1]) / 2
    else:
        offset = (bounds_u[0] + bounds_u[1]) / 2

    pm.optionVar(fv=('polySymmetrizeUVAxisOffset', offset))

def set_symmetry_axis_and_activate_symmetry_brush():
    selection = pm.ls(sl=True)

    # Convert the selection to UVs.
    uvs = pm.polyListComponentConversion(selection, ff=True, fuv=True, fe=True, fvf=True, tuv=True)
    if uvs:
        set_symmetry_axis(uvs)

    pm.setToolTo('texSymmetrizeUVContext')

        
