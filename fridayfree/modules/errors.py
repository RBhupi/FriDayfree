"""Domain errors. Services raise these; the UI turns them into friendly messages."""


class ValidationError(Exception):
    """A user-correctable problem. The message is shown to the user as-is."""
