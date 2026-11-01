  // --- jména z protojazyka: tvar (IPA), přepis a význam ---
  const NAME_MOD = /[̀-ͯʰ-˿]/;
  function nameSegs(s) { const v = []; for (const ch of s) { if (v.length && (NAME_MOD.test(ch) || v[v.length - 1].endsWith('͡'))) v[v.length - 1] += ch; else v.push(ch); } return v; }
  const ROM = { 'kʷ': 'kw', 'ɡʷ': 'gw', 'ɡ': 'g', 'ʃ': 'š', 'ʒ': 'ž', 't͡ʃ': 'č', 'd͡ʒ': 'dž', 't͡s': 'c', 'd͡z': 'dz', 'ŋ': 'ng', 'ɲ': 'ň', 'θ': 'th', 'ð': 'dh',
    'x': 'ch', 'ɣ': 'gh', 'ʔ': '’', 'ə': 'e', 'ɛ': 'e', 'æ': 'ä', 'ø': 'ö', 'ɔ': 'o', 'ʊ': 'u', 'ɪ': 'i', 'y': 'ü', 'ɨ': 'y', 'β': 'v', 'ɸ': 'f', 'χ': 'ch',
    'ʁ': 'r', 'ħ': 'h', 'ɦ': 'h', 'ʎ': 'ľ', 'ɬ': 'hl', 'c': 'ť', 'ɟ': 'ď', 'ɢ': 'g', 'ʋ': 'v', 'ɹ': 'r', 'ɰ': 'g', 'ʝ': 'j', 'ɑ': 'a', 'ɒ': 'o', 'ʌ': 'a' };
  // Složeniny se ve jménech zkracují jako skutečná místní jména: první část na slabiku, celek nejvýš na tři slabiky.
  const NAME_VOWEL = /^[aeiouyæøɛɔəɪʊɨʉɯɤʌœɞɶɑɒɘɵʏ]/;
  function nameSyllables(ipa) {
    const S = nameSegs(ipa), out = [[]];
    S.forEach((x, i) => {
      const cur = out[out.length - 1], hasV = cur.some(y => NAME_VOWEL.test(y));
      if (hasV && (NAME_VOWEL.test(x) || (i + 1 < S.length && NAME_VOWEL.test(S[i + 1])))) out.push([x]); else cur.push(x);
    });
    return out.map(y => y.join(''));
  }
  function compound(parts) {
    const syl = parts.map(nameSyllables), head = syl.slice(0, -1).map(x => x[0]), last = syl[syl.length - 1];
    return [...head, ...last].slice(0, Math.max(2, head.length + 2)).join('');
  }
  const romanize = ipa => { const t = nameSegs(ipa).map(s => ROM[s] ?? s).join(''); return t.charAt(0).toUpperCase() + t.slice(1); };
  const nameSeed = (key, attempt) => [...key].reduce((a, c) => (Math.imul(a, 31) + c.charCodeAt(0)) | 0, 7) + attempt * 7919;
  const NOUNS = {
    plain: [['field', 'n', 'Pole'], ['earth', 'f', 'Země'], ['river', 'f', 'Řeka'], ['road', 'f', 'Cesta'], ['village', 'f', 'Ves'], ['forest', 'm', 'Les'], ['grain', 'n', 'Obilí'], ['horse', 'm', 'Kůň']],
    hills: [['forest', 'm', 'Les'], ['stone', 'm', 'Kámen'], ['tree', 'm', 'Strom'], ['path', 'f', 'Stezka'], ['root', 'm', 'Kořen']],
    mountains: [['mountain', 'f', 'Hora'], ['stone', 'm', 'Kámen'], ['cloud', 'm', 'Mrak'], ['wind', 'm', 'Vítr'], ['thunder', 'm', 'Hrom'], ['star', 'f', 'Hvězda']],
    island: [['sea', 'n', 'Moře'], ['boat', 'f', 'Loď'], ['fish', 'f', 'Ryba'], ['sand', 'm', 'Písek'], ['wind', 'm', 'Vítr']],
  };
  const ADJS = [['big', 'Velk'], ['small', 'Mal'], ['red', 'Červen'], ['white', 'Bíl'], ['black', 'Čern'], ['green', 'Zelen'], ['old', 'Star'],
    ['new', 'Nov'], ['cold', 'Studen'], ['dry', 'Such'], ['long', 'Dlouh'], ['good', 'Dobr'], ['round', 'Kulat']];
  // Jméno kraje: podstatné jméno podle krajiny, často s přívlastkem („Bílá řeka“).
  function placeName(key, terrain, attempt, taken) {
    for (let n = 0; n < 60; n++) {
      const s = nameSeed(key, attempt * 60 + n), h = k => hash(s, k);
      const nouns = NOUNS[terrain] || NOUNS.plain, [nc, gender, nCz] = nouns[Math.floor(h(1) * nouns.length)];
      let ipa, meaning;
      if (h(2) < 0.72) { const [ac, stem] = ADJS[Math.floor(h(3) * ADJS.length)]; ipa = compound([LEX[ac], LEX[nc]]); meaning = `${stem}${{ m: 'ý', f: 'á', n: 'é' }[gender]} ${nCz.toLowerCase()}`; }
      else { ipa = compound([LEX[nc]]); meaning = nCz; }
      const name = romanize(ipa);
      if (!taken.has(name)) return { name, ipa, meaning };
    }
    return { name: romanize(LEX.village) + attempt, ipa: LEX.village, meaning: 'Ves' };
  }
  // Jméno jazyka: jak ho nazývají jeho mluvčí („naše řeč“), a česky odvozené -ština.
  const ENDONYMS = [[['language'], 'řeč'], [['we', 'language'], 'naše řeč'], [['person', 'language'], 'řeč lidí'], [['speak'], 'mluvení'], [['good', 'language'], 'dobrá řeč'], [['person'], 'lidé']];
  function czechLanguage(endonym) {
    let stem = endonym.toLowerCase().replace(/[’]/g, '');
    stem = stem.replace(/[aeiouäöüy]+$/, '') || stem;
    return stem + 'ština';
  }
  function languageName(key, attempt) {
    const s = nameSeed(key, attempt), [parts, meaning] = ENDONYMS[Math.floor(hash(s, 9) * ENDONYMS.length)];
    const ipa = compound(parts.map(p => LEX[p])), endonym = romanize(ipa);
    return { endonym, ipa, meaning, name: czechLanguage(endonym) };
  }
