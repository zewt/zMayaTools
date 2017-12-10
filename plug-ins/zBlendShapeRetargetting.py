import math, inspect, os, sys, time
import pymel.core as pm
import maya.cmds as cmds
from zMayaTools.menus import Menu
from zMayaTools import maya_logging, maya_helpers
from zMayaTools import blend_shape_retargetting

log = maya_logging.get_log()

class PluginMenu(Menu):
    def add_menu_items(self):
        for menu in ['mainDeformMenu', 'mainRigDeformationsMenu']:
            # Make sure the file menu is built.
            pm.mel.eval('ChaDeformationsMenu "MayaWindow|%s";' % menu)

            for item in pm.menu(menu, q=True, ia=True):
                # Find the "Edit" section.
                if pm.menuItem(item, q=True, divider=True):
                    section = pm.menuItem(item, q=True, label=True)
                if section != 'Edit':
                    continue

                # Find the "Blend Shape" submenu.
                if not pm.menuItem(item, q=True, subMenu=True):
                    continue
                if pm.menuItem(item, q=True, label=True) != 'Blend Shape':
                    continue

                self.add_menu_item('zBlendShapeRetargetting_%s' % menu, label='Retarget Blend Shapes', parent=item,
                        command=lambda unused: blend_shape_retargetting.UI().run())

menu = PluginMenu()
def initializePlugin(mobject):
    menu.add_menu_items()

def uninitializePlugin(mobject):
    menu.remove_menu_items()

