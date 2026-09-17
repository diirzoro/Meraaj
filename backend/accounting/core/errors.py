class AccountingError(Exception):
    """Single error type raised by the Accounting Core.

    `code` is a stable machine-readable identifier (never translated); `message` is the
    human-facing text. The Core never raises HTTP exceptions — the adapter/API layer maps
    `code`/`http_status` onto transport errors, which keeps the Core portable.
    """

    def __init__(self, code: str, message: str, http_status: int = 400, **details):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.details = details

    def to_dict(self) -> dict:
        return {"error": self.code, "detail": self.message, **self.details}
