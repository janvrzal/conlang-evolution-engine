# Výkonnostní benchmarky

Benchmark simulátoru je záměrně oddělený od unit testů: neporovnává náhodné
výsledky, ale měří teplý běh nad deterministickým syntetickým lexikonem.

```bash
.venv/bin/python scripts/benchmark_simulation.py --lexemes 2000 --years 1000 --repetitions 3
.venv/bin/python scripts/benchmark_simulation.py --lexemes 2000 --years 1000 --repetitions 3 --genealogy
```

První příkaz měří vlastní vývoj, druhý i tvorbu genealogické historie. Výstup
je JSON s mediánem času a maximální špičkou paměti. Výsledky se necommitují;
po zavedení baseline se z nich vytvoří regresní limit v samostatném CI jobu.
