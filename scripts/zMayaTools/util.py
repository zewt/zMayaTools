def scale(x, l1, h1, l2, h2):
    """
    Scale x from the range [l1,h1] to the range [l2,h2].
    """
    return (x - l1) * (h2 - l2) / (h1 - l1) + l2

class ProgressWindow(object):
    def __init__(self, total_progress_values=10, title=''):
        self._cancel = False

    def hide(self):
        pass

    def cancel(self):
        self._cancel = True

    def set_total_progress_value(self, total_progress_values):
        """
        Change the number of total progress values.

        Once progress has started the total shouldn't be changed, since progress
        bars should never go backwards, but this can be useful to create the
        window before the total amount of work to do is known.
        """
        raise NotImplementedError

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


