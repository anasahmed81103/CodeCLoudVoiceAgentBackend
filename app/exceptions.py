"""Domain errors that always serialize to the {data, error} envelope."""


class APIError(Exception):
    def __init__(
        self,
        status_code: int,
        message: str,
        details: list[dict] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = str(message)
        self.details = details
