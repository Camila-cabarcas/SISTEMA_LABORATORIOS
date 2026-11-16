"""
backends.py — users
Backend de autenticación que acepta, en el mismo campo, el nombre de usuario
o el correo electrónico.

Orden de búsqueda:
1. username exacto — el comportamiento de siempre de Django, para que nadie
   que ya entraba con su usuario deje de poder hacerlo.
2. username o email sin distinguir mayúsculas, solo si identifica a UNA
   cuenta. Si hay ambigüedad (dos cuentas que coinciden) no se autentica a
   ninguna: es preferible un login fallido a entrar en la cuenta equivocada.

Hereda de ModelBackend, así que permisos, is_active y demás siguen igual.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q


class UsuarioOCorreoBackend(ModelBackend):

    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)
        if username is None or password is None:
            return None
        identificador = username.strip()
        if not identificador:
            return None

        usuario = self._buscar(UserModel, identificador)
        if usuario is None:
            # Igual que ModelBackend: hashear de todas formas para que el
            # tiempo de respuesta no revele si la cuenta existe.
            UserModel().set_password(password)
            return None

        if usuario.check_password(password) and self.user_can_authenticate(usuario):
            return usuario
        return None

    @staticmethod
    def _buscar(UserModel, identificador):
        manager = UserModel._default_manager
        exacto = manager.filter(username=identificador).first()
        if exacto is not None:
            return exacto

        candidatos = list(
            manager.filter(
                Q(username__iexact=identificador)
                | (Q(email__iexact=identificador) & ~Q(email=''))
            )[:2]
        )
        if len(candidatos) == 1:
            return candidatos[0]
        return None
