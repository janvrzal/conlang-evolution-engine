// Postup běhu na ikoně aplikace: Dock (macOS) a hlavní panel (Windows). Jen v aplikaci Tauri.
let last: number | null | undefined;

/** p ∈ ⟨0, 1⟩ během běhu, null = bez ukazatele */
export async function dockProgress(p: number | null) {
	const pct = p == null ? null : Math.round(Math.max(0, Math.min(1, p)) * 100);
	if (pct === last) return;
	last = pct;
	try {
		const { getCurrentWindow, ProgressBarStatus } = await import('@tauri-apps/api/window');
		await getCurrentWindow().setProgressBar(pct == null ? { status: ProgressBarStatus.None } : { status: ProgressBarStatus.Normal, progress: pct });
	} catch {
		// systém ukazatel nepodporuje: nic se neděje
	}
}
