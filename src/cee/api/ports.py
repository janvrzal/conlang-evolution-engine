"""Hledání volného portu pro lokální API server."""
import socket
from contextlib import closing

DEFAULT_PORT = 8000
SCAN_RANGE = 20

# Podpis, podle kterého klient pozná, že na portu opravdu sedí CEE, a ne
# jiná lokální aplikace, která taky odpovídá na /api/health.
ENGINE_SIGNATURE = "Conlang Evolution Engine"


def is_port_free(port: int, host: str = "127.0.0.1") -> bool:
    """True, pokud na daném portu nikdo neposlouchá a lze se na něj navázat."""
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
        return True


def find_free_port(preferred: int = DEFAULT_PORT, host: str = "127.0.0.1",
                   scan_range: int = SCAN_RANGE) -> int:
    """
    Vrátí volný port: nejdřív zkusí `preferred`, pak `scan_range` portů nad ním,
    a když ani jeden nevyjde, nechá port přidělit systémem.

    Rozsah je záměrně malý a začíná u preferovaného portu, aby klient dokázal
    server najít prohledáním stejného rozsahu.
    """
    for port in range(preferred, preferred + scan_range + 1):
        if is_port_free(port, host):
            return port

    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind((host, 0))
        return sock.getsockname()[1]
