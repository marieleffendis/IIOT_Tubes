// Index.js — komunikasi dashboard dengan backend Dobot (index.py)

const STATUS_POLL_MS = 3000;

document.addEventListener('DOMContentLoaded', () => {
    initAxisButtons();
    initToggleButtons();
    initReconnectButton();
    initHomeButton();

    refreshStatus();
    setInterval(refreshStatus, STATUS_POLL_MS);
});

// --- Sumbu X / Y / Z / R (jog relatif) ------------------------------------
function initAxisButtons() {
    document.querySelectorAll('.axis-control[data-axis="x"], .axis-control[data-axis="y"], .axis-control[data-axis="z"], .axis-control[data-axis="r"]')
        .forEach((block) => {
            const axis = block.dataset.axis; // "x", "y", "z", atau "r"
            block.querySelectorAll('button[data-direction]').forEach((button) => {
                button.addEventListener('click', () => {
                    sendJog(axis, button.dataset.direction, button);
                });
            });
        });
}

async function sendJog(axis, direction, button) {
    setButtonBusy(button, true);
    try {
        const res = await fetch('/api/jog', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ axis, direction }),
        });
        const data = await res.json();
        if (data.ok) {
            updatePoseReadout(data.pose);
        } else {
            console.warn(`Jog ${axis}/${direction} gagal:`, data.error);
        }
    } catch (err) {
        console.error('Gagal mengirim perintah jog:', err);
    } finally {
        setButtonBusy(button, false);
    }
}

// --- Suction & Conveyor (toggle Hidup/Mati) ----------------------------
function initToggleButtons() {
    document.querySelectorAll('.axis-control[data-axis="suction"], .axis-control[data-axis="conveyor"]')
        .forEach((block) => {
            const axis = block.dataset.axis; 
            block.querySelectorAll('button').forEach((button) => {
                button.addEventListener('click', () => {
                    const enable = button.classList.contains('btn-on');
                    sendToggle(axis, enable, button);
                });
            });
        });
}

async function sendToggle(axis, enable, button) {
    setButtonBusy(button, true);
    try {
        const res = await fetch(`/api/${axis}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ state: enable }),
        });
        const data = await res.json();
        if (!data.ok) {
            console.warn(`${axis} gagal:`, data.error);
        }
    } catch (err) {
        console.error(`Gagal mengirim perintah ${axis}:`, err);
    } finally {
        setButtonBusy(button, false);
    }
}

// --- Status koneksi & tombol reconnect ---------------------------------
function initReconnectButton() {
    const btn = document.getElementById('reconnectBtn');
    if (!btn) return;

    btn.addEventListener('click', async () => {
        btn.disabled = true;
        const originalText = btn.textContent;
        btn.textContent = 'Menghubungkan...';
        try {
            const res = await fetch('/api/connect', { method: 'POST' });
            const data = await res.json();
            applyStatus(data);
        } catch (err) {
            console.error('Gagal menyambungkan ke Dobot:', err);
        } finally {
            btn.disabled = false;
            btn.textContent = originalText;
        }
    });
}

// --- Home ulang manual (POST /api/home) ---------------------------------
function initHomeButton() {
    const btn = document.getElementById('homeBtn');
    if (!btn) return;

    btn.addEventListener('click', async () => {
        const confirmed = window.confirm(
            'Jalankan homing ulang? Pastikan area sekitar lengan robot kosong. Proses ini memakan waktu ±20 detik.'
        );
        if (!confirmed) return;

        btn.disabled = true;
        const originalText = btn.textContent;
        btn.textContent = 'Homing...';
        try {
            const res = await fetch('/api/home', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ force: true }),
            });
            const data = await res.json();
            applyStatus(data);
            if (!data.ok) {
                console.warn('Homing gagal:', data.error);
            }
        } catch (err) {
            console.error('Gagal memicu homing:', err);
        } finally {
            btn.disabled = false;
            btn.textContent = originalText;
        }
    });
}

async function refreshStatus() {
    try {
        const res = await fetch('/api/status');
        const data = await res.json();
        applyStatus(data);
    } catch (err) {
        applyStatus({ connected: false });
    }
}

function applyStatus(data) {
    setConnectionStatus(!!data.connected);
    if (data.pose) updatePoseReadout(data.pose);
    updateHomingBanner(!!data.homing);
    setControlsLocked(!!data.homing);
}

function updateHomingBanner(isHoming) {
    const banner = document.getElementById('homingBanner');
    if (!banner) return;
    banner.classList.toggle('is-active', isHoming);
}

function setControlsLocked(locked) {
    document
        .querySelectorAll(
            '.axis-control[data-axis="x"] button, ' +
            '.axis-control[data-axis="y"] button, ' +
            '.axis-control[data-axis="z"] button, ' +
            '.axis-control[data-axis="r"] button, ' +
            '.axis-control[data-axis="suction"] button, ' +
            '.axis-control[data-axis="conveyor"] button'
        )
        .forEach((btn) => {
            btn.disabled = locked;
        });
}

function setConnectionStatus(isConnected) {
    const statusDot = document.querySelector('.status-dot');
    const statusText = document.getElementById('statusText');
    if (!statusDot || !statusText) return;

    if (isConnected) {
        statusDot.style.backgroundColor = 'var(--status-online)';
        statusDot.style.boxShadow = '0 0 0 3px rgba(16, 185, 129, 0.2)';
        statusText.textContent = 'Dobot Terhubung';
    } else {
        statusDot.style.backgroundColor = 'var(--status-offline)';
        statusDot.style.boxShadow = '0 0 0 3px rgba(248, 113, 113, 0.2)';
        statusText.textContent = 'Dobot Tidak Terhubung';
    }
}

function updatePoseReadout(pose) {
    const el = document.getElementById('poseReadout');
    if (!el || !pose) return;
    el.textContent = `Posisi: X ${pose.x.toFixed(1)}  Y ${pose.y.toFixed(1)}  Z ${pose.z.toFixed(1)}  R ${pose.r.toFixed(1)}`;
}

function setButtonBusy(button, busy) {
    if (!button) return;
    button.disabled = busy;
    button.style.opacity = busy ? '0.5' : '';
}