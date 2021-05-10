# zReorderAttribute is used to reorder user-defined attributes.
#
# zReorderAttribute -dir down -attr node.attr1 -attr node.attr2
#
# If multiple attributes are given, they'll be grouped together.  If they weren't previously
# grouped, they'll be moved relative to the first attribute found.
#
# -dir specifies the direction to move the attributes: up, down, top, or bottom.
#
# Attributes can be specified that live on different nodes, to allow batch reordering attributes
# on multiple similar selected nodes.

import pymel.core as pm
from maya import OpenMaya as om, OpenMayaMPx as ompx
from zMayaTools import maya_helpers

from zMayaTools import maya_logging
log = maya_logging.get_log()

class CommandError(Exception):
    def __init__(self, message):
        super(CommandError, self).__init__(self, message)
        self.message = message

class ReorderAttribute(ompx.MPxCommand):
    @classmethod
    def register(cls, plugin):
        plugin.registerCommand('zReorderAttribute', cls.create, cls.create_syntax)

    @classmethod
    def unregister(cls, plugin):
        plugin.deregisterCommand('zReorderAttribute')

    @classmethod
    def create(cls):
        return ompx.asMPxPtr(cls())

    @classmethod
    def create_syntax(cls):
        syntax = om.MSyntax()

        syntax.addFlag('', '-attr', om.MSyntax.kString)
        syntax.makeFlagMultiUse('-attr')
        
        syntax.addFlag('-dir', '-direction', om.MSyntax.kString)

        return syntax

    def isUndoable(self):
        return self.undoable

    def doIt(self, args):
        self.undoable = True

        try:
            # Work around an OpenMaya bug.  Normally, if arguments are invalid you return kFailure.
            # MArgDatabase will already have printed an error and the command will be cancelled.  If we
            # do that in Python, it prints a stack trace and an "Unexpected Internal Failure" exception.
            # We have to work around this by returning success, and returning false from isUndoable so
            # the command isn't put on the undo stack.
            try:
                arg_db = om.MArgDatabase(self.syntax(), args)
            except Exception as e:
                raise CommandError('')

            direction = 'down'
            if arg_db.isFlagSet('-dir'):
                direction = arg_db.flagArgumentString('-dir', 0)
            if direction not in ('up', 'down', 'top', 'bottom'):
                raise CommandError('-dir must be one of; up, down, top, bottom')

            # We should be able to use kSelectionItem for this, but for some reason that reduces
            # the argument to the node and won't pass attributes through, so we have to handle it
            # manually.
            cnt = arg_db.numberOfFlagUses('-attr')
            attrs = []
            for idx in range(cnt):
                this_arg = om.MArgList()
                arg_db.getFlagArgumentList('-attr', idx, this_arg)
                arg = this_arg.asString(0)

                try:
                    attr = pm.PyNode(arg)
                except pm.MayaObjectError:
                    raise CommandError('Invalid attribute: %s' % arg)

                if not isinstance(attr, pm.general.Attribute):
                    raise CommandError('Invalid attribute: %s' % arg)

                # Check that all specified attributes are userDefined.  We can't move built-in attributes.
                if not attr.isDynamic():
                    raise CommandError('Attribute isn\'t user-defined: %s' % attr)

                # We can't move attributes on referenced nodes.
                if pm.referenceQuery(attr.node(), isNodeReferenced=True):
                    raise CommandError('Can\'t reorder attributes on referenced node: %s', attr)

                attrs.append(attr)

            # Store the original order for undo.
            nodes = {attr.node() for attr in attrs}
            self.original_attr_order = {}
            for node in nodes:
                self.original_attr_order[node] = pm.listAttr(node, userDefined=True)

            # Make the attribute list that we'll apply.
            self.create_new_attribute_list(direction, attrs)
        except CommandError as e:
            # If this is empty, the error was already printed.
            if e.message:
                log.error(e.message)

            self.undoable = False
            return
        except:
            self.undoable = False
            raise

        self.redoIt()

    def create_new_attribute_list(self, direction, attrs):
        """
        Move the given attributes up or down.
        """
        assert direction in ('up', 'down', 'top', 'bottom'), direction

        # Attributes might be selected on more than one node.  Group them by node and process
        # them separately.
        nodes = {attr.node() for attr in attrs}
        self.new_attribute_order = {}
        for node in nodes:
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
            
            if direction == 'down' and group3:
                # Take the first attribute in group3 and put it at the end of group1.
                group1.append(group3[0])
                group3[:1] = []
            elif direction == 'up' and group1:
                # Take the last attribute in group1 and put it at the beginning of group3.
                group3[0:0] = [group1[-1]]
                group1[-1:] = []
            elif direction == 'top':
                # Swap group1 and group2.
                group1, group2 = group2, group1
                pass
            elif direction == 'bottom':
                # Swap group2 and group3.
                group2, group3 = group3, group2
            
            new_attr_list = group1 + group2 + group3
            self.new_attribute_order[node] = new_attr_list

    def redoIt(self):
        for node, attrs in self.new_attribute_order.items():
            self.set_attribute_order(node, attrs)

    def undoIt(self):
        for node, attrs in self.original_attr_order.items():
            self.set_attribute_order(node, attrs)

    @classmethod
    def set_attribute_order(cls, node, attrs):
        """
        Set the order of all user attributes on node.
        
        attrs should contain all user attributes.  If any are missing from the list,
        they'll end up at the top.
        """
        # Sanity check the attribute list before making any changes.
        for attr in reversed(attrs):
            attr = node.attr(attr)
        
        # Deleting an attribute and undoing the deletion pushes an attribute to the end of
        # the list.
        #
        # Do this with MDGModifier, since regular high-level undo will spam undo logs to
        # the script editor.
        for attr in attrs:
            # For some reason, Maya won't delete a locked attribute.
            attr = node.attr(attr)
            locked = pm.getAttr(attr, lock=True)
            if locked:
                pm.setAttr(attr, lock=False)

            mod = om.MDGModifier()
            mod.removeAttribute(attr.node().__apimobject__(), attr.__apimobject__())
            mod.doIt()
            mod.undoIt()

            # Re-lock attributes.
            if locked:
                pm.setAttr(attr, lock=True)

