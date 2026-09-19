"""Persistované dotazy nad výsledkem jedné simulace.

Veřejné HTTP API nesmí vědět, zda data leží v JSON souboru nebo v Neo4j.
Tento balíček proto obsahuje malé portové rozhraní a jeho adaptéry.
"""

from cee.storage.genealogy import (
    FileGenealogyStore,
    GenealogyStore,
    Neo4jGenealogyStore,
    get_genealogy_store,
)

__all__ = [
    "FileGenealogyStore",
    "GenealogyStore",
    "Neo4jGenealogyStore",
    "get_genealogy_store",
]
