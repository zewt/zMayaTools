class ProgressWindow(object):
    def __init__(self, total_progress_values=10, title=''):
        self._cancel = False

    def hide(self):
        pass

    def cancel(self):
        self._cancel = True

    def check_cancellation(self):
        if self._cancel:
            raise CancelledException()

    def update(self, advance_by=1, text=''):
        """
        Advance the progress bar.

        This should be called at the start of a task.  For example,

        progress = ProgressWindow(10)
        for idx in xrange(10:
            progress.update()
            work()
        """
        # Check for cancellation when we update progress.
        self.check_cancellation()

    def __enter__(self, *args, **kwargs):
        return self

    def __exit__(self, exc, e, tb):
        self.hide()


