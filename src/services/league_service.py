from sqlalchemy.orm import Session
from src.core.exceptions import LeagueNotPrivateError, PasswordIncorrectError
from src.core.security import verify_password

def check_league_password(session: Session, league_id: int, password: str) -> None:
    league = session.get(league_id)

    if league is None: 
        raise LeagueNotPrivateError("La liga no fue encontrada")

    if league.password_hash is None: 
        raise LeagueNotPrivateError("La liga que se está intentando verificar no es privada")

    if not(verify_password(password, league.password_hash)):
        raise PasswordIncorrectError("La contraseña ingresada no es correcta")

    