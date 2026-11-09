/** Rok s typografickým minusem: −700, 1950. */
export const formatYear = (y: number) => (y < 0 ? `−${Math.abs(Math.round(y))}` : String(Math.round(y)));
