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
from zMayaTools import maya_helpers

# This isn't in the v1 API, but mixing it seems safe.
from maya.api.MDGContextGuard import MDGContextGuard    

from zMayaTools import maya_logging
log = maya_logging.get_log()

def bake_transform(*args, **kwargs):
    with maya_helpers.restores() as restores:
        # Temporarily pause the viewport.
        #
        # This is only needed because the progress window needs to force a refresh, and refreshing
        # makes this 4x slower if viewports are enabled.
        restores.append(maya_helpers.SetAndRestorePauseViewport(True))

        min_frame = int(pm.playbackOptions(q=True, min=True))
        max_frame = int(pm.playbackOptions(q=True, max=True))

        # This should be cancellable, but for some reason the cancel button callback
        # never gets called.
        with maya_helpers.ProgressWindowMaya(1, title='Baking keyframes',
                with_secondary_progress=False, with_cancel=False) as progress:
            return bake_transform_internal(min_frame, max_frame, progress=progress,
                    *args, **kwargs)

def bake_transform_internal(min_frame, max_frame,
        position=True, rotation=True, scale=False, progress=None):
    nodes = pm.ls(sl=True, type='transform')
    if len(nodes) != 2:
        log.info('Select a source and a destination transform')
        return
    src = nodes[0]
    dst = nodes[1]

    # Updating the progress window every frame is too slow, so we only update it
    # every 10 frames.
    update_progress_every = 10
    total_frames = max_frame - min_frame + 1
    progress.set_total_progress_value(total_frames*2 / update_progress_every)

    # Make sure our target attributes aren't locked.  (Can we check if they're writable,
    # eg. disconnected or connected but writable?)
    attributes_to_check = []
    if position:
        attributes_to_check.extend(('t', 'tx', 'ty', 'tz'))
    if rotation:
        attributes_to_check.extend(('r', 'rx', 'ry', 'rz'))
    if scale:
        attributes_to_check.extend(('s', 'sx', 'sy', 'sz'))

    failed = False
    for attr_name in attributes_to_check:
        attr = dst.attr(attr_name)
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

    with maya_helpers.restores() as restores:
        # Disable stepped preview while we do this.
        restores.append(maya_helpers.SetAndRestoreCmd(pm.playbackOptions, key='blockingAnim', value=False))

        # Temporarily disconnect any transform connections.  If there are already keyframes
        # connected, calling pm.matchTransform will have no effect.  These connections will
        # be restored when this restores() block exits.
        def disconnect_attrs(attr):
            for channel in ('x', 'y', 'z'):
                restores.append(maya_helpers.SetAndRestoreAttr(dst.attr(attr + channel), 1))
            restores.append(maya_helpers.SetAndRestoreAttr(dst.attr(attr), (1,1,1)))
        if position: disconnect_attrs('t')
        if rotation: disconnect_attrs('r')
        if scale: disconnect_attrs('s')

        # Read the position on each frame.  We'll read all values, then write all results at once.
        for frame in frame_range:
            if (frame % update_progress_every) == 0:
                progress.update()

            mtime.setValue(frame)
            with MDGContextGuard(om.MDGContext(mtime)) as guard:
                pm.matchTransform(dst, src, pos=True, rot=True, scl=True)

                # Store the resulting transform values.
                values.append((dst.t.get(), dst.r.get(), dst.s.get()))
    
    # Now that the above restores block has exited, any connections to the transform
    # will be restored.  Apply the transforms we stored now that we're no longer in
    # an MDGContext.
    with maya_helpers.restores() as restores:
        # Disable auto-keyframe while we do this.  Otherwise, a keyframe will also
        # be added at the current frame.
        restores.append(maya_helpers.SetAndRestoreCmd(pm.autoKeyframe, key='state', value=False))

        current_frame = pm.currentTime(q=True)

        # Set each destination node's transform on each frame.
        for frame, (t, r, s) in zip(frame_range, values):
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

            if position:
                set_keyframe('tx', t[0])
                set_keyframe('ty', t[1])
                set_keyframe('tz', t[2])
            if rotation:                
                set_keyframe('rx', r[0])
                set_keyframe('ry', r[1])
                set_keyframe('rz', r[2])
            if scale:
                set_keyframe('sx', s[0])
                set_keyframe('sy', s[1])
                set_keyframe('sz', s[2])

