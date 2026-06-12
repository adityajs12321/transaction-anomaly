"""Domain exceptions raised by the service layer.

main.py registers handlers that map these to HTTP status codes, keeping
routers free of error-translation logic.
"""


class InvalidUploadError(Exception):
    """Upload failed validation (extension, encoding, columns, empty)."""


class UploadTooLargeError(Exception):
    """Upload exceeds the configured size limit."""


class JobNotFoundError(Exception):
    """No job exists with the requested id."""


class ResultsNotReadyError(Exception):
    """Results were requested for a job that is not completed."""
