"""
Schemas Pydantic para autenticación (registro y login)
"""

from __future__ import annotations

from pydantic import BaseModel, EmailStr


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

class UserOut(BaseModel):
    """
    Los datos públicos de un usuario, tal como los devuelve el login.
    """
    user_id: int
    team_id: int
    username: str
    email: str


class LoginRequest(BaseModel):
    """
    Lo que se espera recibir en el body de POST /api/v1/auth/login.
    EmailStr valida el formato de mail, asi que si viene mal formado, FastAPI devuelve un 422 automatico
    antes de que el codigo del endpoint llegue a ejecutarse.
    """
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    """
    Lo que devolvemos si el login sale bien (200 OK).
    `user` es un objeto anidado de tipo UserOut, asi Pydantic sabe validar/serializar esos
    cuatro campos como un sub-objeto en el JSON de salida.
    """
    token: str

    # "Bearer" es el esquema de autenticación estándar (RFC 6750): le
    # indica al cliente que debe reenviar este token tal cual en el
    # header "Authorization: Bearer <token>" en cada request futuro.
    # Siempre vale lo mismo, por eso el default (el cliente no lo elige).
    token_type: str = "Bearer"  

    user: UserOut