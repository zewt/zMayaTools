import logging, sys
from pymel import core as pm
from maya import OpenMaya as om

class MayaLogHandler(logging.Handler):
    def emit(self, record):
        s = self.format(record)
        if record.levelname == 'WARNING':
            om.MGlobal.displayWarning(s)
        elif record.levelname in ('ERROR', 'CRITICAL'):
            # Use MGlobal.displayError rather than pm.error, since for some reason pm.error
            # throws an exception instead of just logging an error.
            om.MGlobal.displayError(s)
        elif record.levelname == 'INFO':
            # This prints the message as '# message #', and more importantly shows it in the
            # status bar.
            om.MGlobal.displayInfo(s)
        elif record.levelname == 'DEBUG':
            # Write all messages to sys.__stdout__, which goes to the output window.  Only write
            # debug messages here.  The script editor is incredibly slow and can easily hang Maya
            # for an hour if we have a lot of debug logging on, but the output window is reasonably
            # fast.
            sys.__stdout__.write('%s\n' % s)

log = None
def get_log():
    global log
    if log is None:
        log = logging.getLogger('zMayaTools')

    # Don't propagate logs to the root when we're in Maya.  Maya's default handler for outputting
    # logs to the console is really ugly, so we need to override it.  Clear the handlers list before
    # adding our own, in case this is a reload.
    log.propagate = False
    log.handlers = []
    log.setLevel('DEBUG')
    log.addHandler(MayaLogHandler())

    return log

