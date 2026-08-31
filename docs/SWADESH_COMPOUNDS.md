# Volitelné návrhy složenin pro Swadesh 100

`cee.semantics.swadesh` obsahuje úplný diagnostický seznam Swadesh 100 a
39 kurátorovaných návrhů pro 36 konceptů. Všechny ostatní položky zůstávají
základními kořeny: balíček nesmí vnutit složeninu tam, kde by jazyk přirozeně
použil jednoduchý lexém.

Návrh je dostupný pouze tehdy, když jazyk už má oba zdrojové lexémy. Až po
potvrzení autora se aplikuje přes `MorphologyEvaluator.compound`, takže nese
správný rok vzniku, hranici morfémů a následně podléhá dalším zvukovým změnám.
Například `RAIN` nabízí `SKY + WATER`; výsledná forma závisí výhradně na
kořenech konkrétního jazyka a jeho `compound_head`.

Balíček je pomoc pro worldbuilding, nikoli empirické tvrzení o univerzální
etymologii. Autor může návrh přijmout, změnit nebo nechat cílový koncept jako
samostatný kořen.
