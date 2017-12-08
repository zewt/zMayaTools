import logging, sys
from pymel import core as pm

class MayaLogHandler(logging.Handler):
    def emit(self, record):
        s = self.format(record)
        if record.levelname == 'WARNING':
            pm.warning(s)
        elif record.levelname in ('ERROR', 'CRITICAL'):
            # pm.error shows the error as red in the status bar, but it also only works if
            # you let it throw an exception and kill your script.  It also shows a stack at
            # the place it's called (here), which we don't want.  So, we need to use warning
            # for errors.
            pm.warning(s)
        elif record.levelname == 'INFO':
            print s

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

