from contextvars import ContextVar

# Holds the current request's ID so logs and error responses can include it.
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
