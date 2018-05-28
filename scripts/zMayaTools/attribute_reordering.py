import pymel.core as pm
from zMayaTools import maya_helpers

from zMayaTools import maya_logging
log = maya_logging.get_log()

def set_attribute_order(node, attrs):
    """
    Set the order of all user attributes on node.
    
    attrs should contain all user attributes.  If any are missing from the list,
    they'll end up at the top.
    
    This can't be undone.
    """
    # Sanity check the attribute list before making any changes.
    for attr in reversed(attrs):
        attr = node.attr(attr)
    
    with maya_helpers.restores() as restores:
        # Make sure undo is enabled.
        restores.append(maya_helpers.SetAndRestoreCmd(pm.undoInfo, key='state', value=True))
        
        # Deleting an attribute and undoing the deletion pushes an attribute to the end of
        # the list.
        for attr in attrs:
            # For some reason, Maya won't delete a locked attribute.
            attr = node.attr(attr)
            locked = pm.getAttr(attr, lock=True)
            if locked:
                pm.setAttr(attr, lock=False)

            pm.deleteAttr(attr)
            pm.undo()

            if locked:
                pm.setAttr(attr, lock=True)

def move_selected_attr(down):
    """
    Move all selected attributes in the channel box down (or up if down is false).
    """
    attrs = [pm.PyNode(n) for n in pm.mel.eval('selectedChannelBoxPlugs')]
    if not attrs:
        log.info('Select one or more attributes in the channel box')
        return
    
    # Attributes might be selected on more than one node.  Group them by node and process
    # them separately.
    nodes = {attr.node() for attr in attrs}
    for node in nodes:
        if pm.referenceQuery(node, isNodeReferenced=True):
            log.error('Can\'t reorder attributes on referenced node: %s', node)
            continue

        # listAttrs returns long names, so be sure to use longName here too.
        selected_attrs = [attr.longName() for attr in attrs if attr.node() == node]
        all_attrs = pm.listAttr(node, userDefined=True)
        
        # Group attributes into three groups: attributes before the selection, the selected
        # attributes, and attributes after the selection.
        #
        # If more than one attribute is being moved and they're not contiguous, we'll lump
        # them together then move the entire group.
        grouped_selected_attrs = []
        added_selected_attrs = False
        group1 = []
        group2 = selected_attrs
        group3 = []
        for attr in all_attrs:
            if attr in selected_attrs:
                added_selected_attrs = True
                continue
            if added_selected_attrs:
                group3.append(attr)
            else:
                group1.append(attr)
        
        new_list = group1 + group2 + group3

        # If we're moving attributes down, take the first attribute in group3 and put it at the
        # end of group1.  Otherwise, take the last attribute in group1 and put it at the beginning
        # of group3.
        #
        # If there are no elements to move (there's nowhere to move the selection), run the operation
        # anyway so attribute grouping still happens.
        if down and group3:
            group1.append(group3[0])
            group3[:1] = []
        elif not down and group1:
            group3[0:0] = [group1[-1]]
            group1[-1:] = []
        
        new_attr_list = group1 + group2 + group3
        set_attribute_order(node, new_attr_list)
    
