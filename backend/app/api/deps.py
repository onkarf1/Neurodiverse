from typing import cast

from fastapi import Request

from app.db.health import DatabaseProbe


def get_database_probe(request: Request) -> DatabaseProbe:
    return cast(DatabaseProbe, request.app.state.database_probe)
