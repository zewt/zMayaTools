class ProgressWindow(object):
    def __init__(self):
        self._cancel = False

    def show(self, title, total_progress_values):
        pass

    def hide(self):
        pass

    def cancel(self):
        self._cancel = True

    def check_cancellation(self):
        if self._cancel:
            raise CancelledException()

    def set_main_progress(self, job):
        # Check for cancellation when we update progress.
        self.check_cancellation()

    def set_task_progress(self, label, percent=None, force=False):
        # Check for cancellation when we update progress.
        self.check_cancellation()


