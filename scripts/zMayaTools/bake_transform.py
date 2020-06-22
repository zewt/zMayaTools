# Bake the transform on each frame from one transform to another.
#
# This is similar to the graph editor's keyframe bake (without any smart key reduction),
# but bakes one object to another.  This is useful for baking a constraint to another
# transform.
#
# For example, you can constrain a locator to a character's hand, and then bake the
# locator to another locator.  The second locator then has the position of the character's
# hand on each frame, so you can constrain other things to it without creating a DG
# dependency between the objects.
#
# This can also be used to bake history-dependent behavior like dynamics to keyframes.
import math, time
import pymel.core as pm
from maya import OpenMaya as om
from maya import OpenMayaAnim as oma
from zMayaTools import maya_helpers, util

# This isn't in the v1 API, but mixing it seems safe.
from maya.api.MDGContextGuard import MDGContextGuard    

from zMayaTools import maya_logging
log = maya_logging.get_log()

def bake_transform(*args, **kwargs):
    nodes = pm.ls(sl=True, type='transform')
    if len(nodes) != 2:
        log.info('Select a source and a destination transform')
        return

    with maya_helpers.restores() as restores:
        min_frame = int(pm.playbackOptions(q=True, min=True))
        max_frame = int(pm.playbackOptions(q=True, max=True))

        src, dst = nodes

        with maya_helpers.ProgressWindowMaya(1, title='Baking keyframes to %s' % dst.nodeName(),
                with_secondary_progress=False, with_cancel=True) as progress:
            try:
                bake = BakeNode(src, dst)
                bake_transform_internal([bake], min_frame, max_frame, progress=progress,
                        *args, **kwargs)
            except util.CancelledException:
                log.info('Bake cancelled')

class BakeNode(object):
    """
    This specifies a bake to perform in bake_transform_internal.
    """
    def __init__(self, src, dst, position=True, rotation=True, scale=True):
        self.src = src
        self.dst = dst
        self.position = position
        self.rotation = rotation
        self.scale = scale

def bake_transform_internal(bakes, min_frame, max_frame, progress=None):
    # Updating the progress window every frame is too slow, so we only update it
    # every 10 frames.
    update_progress_every = 10
    total_frames = max_frame - min_frame + 1

    total_progress_updates = 0
    total_progress_updates += total_frames # frame updates
    total_progress_updates += total_frames*len(bakes) # setting keyframes
    progress.set_total_progress_value(total_progress_updates / update_progress_every)

    # Make sure our target attributes aren't locked.  (Can we check if they're writable,
    # eg. disconnected or connected but writable?)
    failed = False
    for bake in bakes:
        attributes_to_check = []
        if bake.position:
            attributes_to_check.extend(('t', 'tx', 'ty', 'tz'))
        if bake.rotation:
            attributes_to_check.extend(('r', 'rx', 'ry', 'rz'))
        if bake.scale:
            attributes_to_check.extend(('s', 'sx', 'sy', 'sz'))

        for attr_name in attributes_to_check:
            attr = bake.dst.attr(attr_name)
            if attr.get(lock=True):
                log.error('Attribute %s is locked', attr)
                failed = True

    if failed:
        return

    # Match the transform to the target on each frame.  Don't set keyframes while in
    # an MDGContext (this confuses Maya badly).  Just store the results.
    mtime = om.MTime()
    frame_range = range(min_frame, max_frame+1)
    values = []
    for _ in range(len(bakes)):
        values.append([])

    with maya_helpers.restores() as restores:
        # Disable stepped preview while we do this.
        restores.append(maya_helpers.SetAndRestoreCmd(pm.playbackOptions, key='blockingAnim', value=False))

        # Temporarily disconnect any transform connections.  If there are already keyframes
        # connected, calling pm.matchTransform will have no effect.  These connections will
        # be restored when this restores() block exits.
        for bake in bakes:
            def disconnect_attrs(attr):
                for channel in ('x', 'y', 'z'):
                    restores.append(maya_helpers.SetAndRestoreAttr(bake.dst.attr(attr + channel), 1))
                restores.append(maya_helpers.SetAndRestoreAttr(bake.dst.attr(attr), (1,1,1)))
            if bake.position: disconnect_attrs('t')
            if bake.rotation: disconnect_attrs('r')
            if bake.scale: disconnect_attrs('s')

        # Read the position on each frame.  We'll read all values, then write all results at once.
        for frame in frame_range:
            if (frame % update_progress_every) == 0:
                progress.update()

            mtime.setValue(frame)
            with MDGContextGuard(om.MDGContext(mtime)) as guard:
                for idx, bake in enumerate(bakes):
                    pm.matchTransform(bake.dst, bake.src, pos=True, rot=True, scl=True)

                    # Store the resulting transform values.
                    values[idx].append((bake.dst.t.get(), bake.dst.r.get(), bake.dst.s.get()))
    
    # Now that the above restores block has exited, any connections to the transform
    # will be restored.  Apply the transforms we stored now that we're no longer in
    # an MDGContext.
    with maya_helpers.restores() as restores:
        # Disable auto-keyframe while we do this.  Otherwise, a keyframe will also
        # be added at the current frame.
        restores.append(maya_helpers.SetAndRestoreCmd(pm.autoKeyframe, key='state', value=False))

        current_frame = pm.currentTime(q=True)

        # Set each destination node's transform on each frame.
        for idx, values_for_node in enumerate(values):
            dst = bakes[idx].dst

            for frame, (t, r, s) in zip(frame_range, values_for_node):
                if (frame % update_progress_every) == 0:
                    progress.update()

                # Work around some character set quirks.  If we set a keyframe with
                # pm.setKeyframe on the current frame, we need to also set it explicitly
                # on the attribute too, or else the keyframe won't always have the
                # correct value.
                def set_keyframe(attr, value):
                    if frame == current_frame:
                        dst.attr(attr).set(value)
                    pm.setKeyframe(dst, at=attr, time=frame, value=value)

                if bake.position:
                    set_keyframe('tx', t[0])
                    set_keyframe('ty', t[1])
                    set_keyframe('tz', t[2])
                if bake.rotation:                
                    set_keyframe('rx', r[0])
                    set_keyframe('ry', r[1])
                    set_keyframe('rz', r[2])
                if bake.scale:
                    set_keyframe('sx', s[0])
                    set_keyframe('sy', s[1])
                    set_keyframe('sz', s[2])

