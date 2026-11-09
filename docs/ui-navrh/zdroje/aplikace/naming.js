// Jména jazyků a nářečí z faktů enginu (česky). Port desktop/src/lib/naming.ts.
const NAMING = (() => {
  const MOD = /[̀-ͯʰ-˿]/;
  function segments(ipa) {
    const out = [];
    for (const ch of ipa) {
      if (out.length && (MOD.test(ch) || out[out.length - 1].endsWith('͡'))) out[out.length - 1] += ch;
      else out.push(ch);
    }
    return out;
  }
  const ROMAN = {
    'kʷ': 'kw', 'ɡʷ': 'gw', 'ɡ': 'g', 'ʃ': 'š', 'ʒ': 'ž', 't͡ʃ': 'č', 'd͡ʒ': 'dž', 't͡s': 'c', 'd͡z': 'dz', 'ŋ': 'ng', 'ɲ': 'ň',
    'θ': 'th', 'ð': 'dh', 'x': 'ch', 'ɣ': 'gh', 'ʔ': '’', 'ə': 'e', 'ɛ': 'e', 'æ': 'ä', 'ø': 'ö', 'ɔ': 'o', 'ʊ': 'u', 'ɪ': 'i', 'y': 'ü',
    'ɨ': 'y', 'β': 'v', 'ɸ': 'f', 'χ': 'ch', 'ʁ': 'r', 'ħ': 'h', 'ɦ': 'h', 'ʎ': 'ľ', 'ɬ': 'hl', 'c': 'ť', 'ɟ': 'ď', 'ɢ': 'g', 'ʋ': 'v',
    'ɹ': 'r', 'ɰ': 'g', 'ʝ': 'j', 'ɑ': 'a', 'ɒ': 'o', 'ʌ': 'a', 'ɯ': 'y', 'ɤ': 'e', 'œ': 'ö', 'ɘ': 'e', 'ɵ': 'ö', 'ʉ': 'ü', 'ɾ': 'r', 'ɦ': 'h', 'ɱ': 'm', 'ʋ': 'v', 'ɐ': 'a', 'ɜ': 'e', 'ɞ': 'ö', 'ʏ': 'ü', 'ɶ': 'ö', 'ʍ': 'w', 'ɕ': 'š', 'ʑ': 'ž', 'ʂ': 'š', 'ʐ': 'ž', 'ɭ': 'l', 'ɳ': 'n', 'ʈ': 't', 'ɖ': 'd', 'ɻ': 'r',
  };
  function romanize(ipa) {
    const text = segments(ipa).map((s) => { if (ROMAN[s]) return ROMAN[s]; const base = s.replace(MOD, ''); return ROMAN[base] ?? base; }).join('');
    return text.charAt(0).toUpperCase() + text.slice(1);
  }
  const stem = (name) => {
    const lower = name.toLowerCase().replace(/’/g, '');
    return lower.length > 3 ? lower.replace(/[aeiouyäöü]+$/, '') || lower : lower;
  };
  function regionAdjective(name, gender = 'f') {
    const end = { m: 'ý', f: 'á', n: 'é' }[gender];
    const base = stem(name);
    if (/[kc]$/.test(base)) return `${base.slice(0, -1)}ck${end}`;
    if (/s$/.test(base)) return `${base}k${end}`;
    return `${base}sk${end}`;
  }
  const fromEndonym = (endonym) => `${stem(endonym)}ština`;
  function languageNames(languages) {
    const names = new Map(), taken = new Set();
    for (const l of languages) {
      const endonym = l.endonym ? romanize(l.endonym) : l.id;
      let name = fromEndonym(endonym);
      const parent = l.parent ? names.get(l.parent) : null;
      if (taken.has(name) && l.origin) name = `${regionAdjective(l.origin, 'f')} ${parent ?? name}`;
      let unique = name;
      for (let n = 2; taken.has(unique); n++) unique = `${name} ${n}`;
      taken.add(unique); names.set(l.id, unique);
    }
    return names;
  }
  const DIRECTION = { center: 'střední', north: 'severní', south: 'jižní', east: 'východní', west: 'západní',
    northeast: 'severovýchodní', northwest: 'severozápadní', southeast: 'jihovýchodní', southwest: 'jihozápadní' };
  const TERRAIN = { mountains: 'horské', island: 'ostrovní', hills: 'podhorské' };
  function dialectNames(dialects, regionName) {
    const levels = dialects.map((d) => {
      const region = d.regions.length ? regionName(d.regions[0]) : null;
      const regional = region === null ? null : regionAdjective(region, 'n');
      const first = TERRAIN[d.terrain ?? ''] ?? DIRECTION[d.direction] ?? DIRECTION.center;
      return [first, regional, regional && `${DIRECTION[d.local ?? 'center']} ${regional}`].filter(Boolean);
    });
    const pick = dialects.map(() => 0);
    for (let round = 0; round < 3; round++) {
      const count = new Map();
      levels.forEach((l, i) => count.set(l[pick[i]], (count.get(l[pick[i]]) ?? 0) + 1));
      levels.forEach((l, i) => { if ((count.get(l[pick[i]]) ?? 0) > 1 && pick[i] + 1 < l.length) pick[i] += 1; });
    }
    const used = new Map();
    return dialects.map((d, i) => {
      if (d.sole) return 'jednotná řeč';
      const label = levels[i][pick[i]];
      const n = (used.get(label) ?? 0) + 1; used.set(label, n);
      return `${n > 1 ? `${label} ${n}` : label} nářečí`;
    });
  }
  return { segments, romanize, regionAdjective, languageNames, dialectNames };
})();
