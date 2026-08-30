"""Hledání volného portu pro lokální API server."""
import socket
from contextlib import closing

DEFAULT_PORT = 8000
SCAN_RANGE = 20

# Podpis, podle kterého klient pozná, že na portu opravdu sedí CEE, a ne
# jiná lokální aplikace, která taky odpovídá na /api/health.
ENGINE_SIGNATURE = "Conlang Evolution Engine"

# Revize HTTP rozhraní. Zvyš při každé změně, kterou frontend potřebuje —
# nový endpoint, jiný tvar odpovědi. Klient podle ní pozná, že mluví se
# zastaralým serverem, a řekne uživateli, ať ho restartuje, místo aby ho
# nechal hádat nad holým 404.
#
# 1: /api/simulate, /api/simulate_dynamic, /api/protolang/generate
# 2: + /api/evolve (vývoj jedné linie s historií)
# 3: + /api/projects (persistence), ID projektu smí mít diakritiku
# 4: běhy simulace adresované vlastním ID, lokální souborové úložiště a export
# 5: genealogie v2 (události, prozodie a morfologická metadata)
API_REVISION = 5


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
