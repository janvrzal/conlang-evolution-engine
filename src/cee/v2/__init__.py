"""Engine v2: simulace jazykové změny jako variace, selekce a šíření.

Celý engine běží v Rustu (``rust/cee_engine``, popis ``docs/engine-v2/19-engine-v-rustu.md``).
Python tu drží jen to, co potřebuje server: schéma popisu světa a validaci polí (``spec``),
popis metaparametrů pro UI (``parameters``) a běh na pozadí přes vazbu ``cee_engine_py`` (``runner``).
Návrh a specifikace jsou v ``docs/engine-v2/``.
"""
