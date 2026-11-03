"""Výkon enginu v2 na světě velikosti, jakou bude stavět UI (popis ``cee.v2.spec``).

Mřížka ``rows × columns`` regionů 40 km od sebe, tři protojazyky ve
svislých pásech, stát nad celou mapou s politikou ``promoted`` a od
poloviny běhu spisovný jazyk se školou. Měří se čas běhu přes
``runner`` (jako v UI), počet skupin na konci a velikost exportu.

Použití:  python scripts/v2_spec_timing.py --rows 4 --columns 6 --villages 5 --years 3000

S ``--vocabulary N`` běží svět se slovníkem o ``N`` pojmech (``WorldSpec.vocabulary``)
a skript vypíše i špičkovou paměť procesu. Pro srovnání velikostí slovníku pouštěj
každou zvlášť (jeden proces na měření), například
``--rows 2 --columns 3 --years 1000 --vocabulary 500``.
"""

from __future__ import annotations

import argparse
import json
import resource
import sys
import time
from typing import Any

from cee.v2 import runner


def grid_spec(
    rows: int, columns: int, villages: int, years: float, semantics: bool, vocabulary: int = 149
) -> dict[str, Any]:
    ids = [[f"r{row}c{column}" for column in range(columns)] for row in range(rows)]
    regions = []
    for row in range(rows):
        for column in range(columns):
            neighbours = [ids[r][c] for r, c in ((row - 1, column), (row + 1, column), (row, column - 1),
                                                 (row, column + 1)) if 0 <= r < rows and 0 <= c < columns]
            regions.append({
                "id": ids[row][column], "position": [40.0 * column, 40.0 * row], "neighbours": neighbours,
                "villages": villages, "language": "abc"[min(2, 3 * column // columns)],
                "density": 2.0 if (row, column) == (0, 0) else 1.0,
                "terrain": "mountains" if column == columns - 1 else "plain",
            })
    everything = [region["id"] for region in regions]
    return {
        "end_year": years, "semantics": semantics, "vocabulary": vocabulary,
        "languages": [{"id": "a"}, {"id": "b", "grammar": "substrate"}, {"id": "c", "grammar": "full"}],
        "regions": regions,
        "events": [
            {"kind": "state", "year": 0, "id": "k", "regions": everything, "capital": ids[0][0], "policy": "promoted"},
            {"kind": "standard", "year": years / 2, "of": "k"},
            {"kind": "schools", "year": years / 2, "of": "k"},
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=3)
    parser.add_argument("--columns", type=int, default=4)
    parser.add_argument("--villages", type=int, default=4)
    parser.add_argument("--years", type=float, default=2000.0)
    parser.add_argument("--no-semantics", action="store_true")
    parser.add_argument("--vocabulary", type=int, default=149, help="velikost slovníku (pojmů)")
    args = parser.parse_args()
    spec = grid_spec(args.rows, args.columns, args.villages, args.years, not args.no_semantics, args.vocabulary)
    started = time.perf_counter()
    run, simulation = runner.prepare("timing", spec)
    built = time.perf_counter() - started
    run.execute(simulation)
    total = time.perf_counter() - started
    assert run.status == "done", run.error
    size = len(json.dumps(run.result)) / 1024
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == "darwin" else 1024) / 2**20
    print(f"slovník {args.vocabulary}, špičková paměť {peak:.0f} MB; regionů {args.rows * args.columns}, vesnic {args.rows * args.columns * args.villages}, "
          f"{args.years:.0f} let, sémantika {'ne' if args.no_semantics else 'ano'}: stavba {built:.1f} s, "
          f"celkem {total:.1f} s, skupin na konci {len(simulation.world.groups)}, snímků {len(run.frames)}, "
          f"export {size:.0f} kB")


if __name__ == "__main__":
    main()
