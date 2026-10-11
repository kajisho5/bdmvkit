"""The one exception bdmvkit raises."""


class BdmvError(Exception):
    """A disc cannot be written as asked."""

    def __init__(self, message):
        super().__init__(message)
        self.message = message
