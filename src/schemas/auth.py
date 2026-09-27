"""
Schemas Pydantic para autenticación (registro, y a futuro login).

A propósito estos schemas SOLO validan forma (tipos, presencia de campos).
Las reglas de negocio (vacío-después-de-trim, formato de email, formato de
logo, duplicados) viven en src/services/user_service.py, no acá: así el
error que ve el cliente es siempre {"error": "VOID_USERNAME", ...} — el
shape exacto del contrato — en vez del 422 con lista de loc/msg que arma
Pydantic/FastAPI por defecto ante un ValidationError de schema.
"""

from __future__ import annotations

from pydantic import BaseModel


class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    team_name: str
    team_logo: str


class RegisterResponse(BaseModel):
    user_id: int
    team_id: int
    username: str
    email: str
    team_name: str
    team_logo: str