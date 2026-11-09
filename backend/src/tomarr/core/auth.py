import hashlib
from dataclasses import dataclass
from ipaddress import IPv4Network, IPv6Network, ip_address

from itsdangerous import BadData, URLSafeTimedSerializer
from pwdlib import PasswordHash

_SESSION_SALT = "tomarr.session"

_LOCAL_V4 = tuple(
    IPv4Network(cidr)
    for cidr in ("127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16")
)
_LOCAL_V6 = tuple(IPv6Network(cidr) for cidr in ("::1/128", "fe80::/10", "fc00::/7"))

_password_hash = PasswordHash.recommended()


@dataclass(frozen=True)
class SessionPayload:
    username: str
    fingerprint: str


def is_local_address(host: str | None) -> bool:
    if not host:
        return False
    try:
        address = ip_address(host)
    except ValueError:
        return False
    if address.version == 6 and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    if address.version == 4:
        return any(address in network for network in _LOCAL_V4)
    return any(address in network for network in _LOCAL_V6)


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _password_hash.verify(password, password_hash)


# Lets the login path spend the same verify time when the username is unknown.
DUMMY_HASH = hash_password("tomarr-dummy-password")


def password_fingerprint(password_hash: str) -> str:
    return hashlib.sha256(password_hash.encode()).hexdigest()[:16]


class SessionSigner:
    def __init__(self, secret: str) -> None:
        self._serializer = URLSafeTimedSerializer(secret, salt=_SESSION_SALT)

    def issue(self, username: str, fingerprint: str) -> str:
        return self._serializer.dumps([username, fingerprint])

    def read(self, token: str, max_age: int) -> SessionPayload | None:
        try:
            data: object = self._serializer.loads(token, max_age=max_age)
        except BadData:
            return None
        match data:
            case [str() as username, str() as fingerprint]:
                return SessionPayload(username, fingerprint)
            case _:
                return None
