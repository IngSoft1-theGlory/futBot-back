from __future__ import annotations

from pydantic import BaseModel


class VerifyPasswordRequest(BaseModel):
    password: str

class VerifyPasswordResponse(BaseModel):
    join_token: str
    expires_in_seconds: int