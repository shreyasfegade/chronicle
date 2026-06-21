/**
 * Chronicle — dashboard controller.
 * Owns state (the selected date), fetches data, drives every visualization,
 * and wires up navigation, export, the live clock, and auto-refresh.
 */
const ChronicleApp = (() => {
    const REFRESH_MS = 30000;
    const HEATMAP_DAYS = 84;

    let selected = new Date();
    let categories = {};
    let lastDay = null;
    let booted = false;

    const isoLocal = (date) => {
        const y = date.getFullYear();
        const m = String(date.getMonth() + 1).padStart(2, '0');
        const d = String(date.getDate()).padStart(2, '0');
        return `${y}-${m}-${d}`;
    };
    const sameDay = (a, b) => isoLocal(a) === isoLocal(b);
    const isToday = () => sameDay(selected, new Date());

    async function getJSON(url) {
        const res = await fetch(url);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
    }

    async function init() {
        try {
            categories = await getJSON('/api/categories');
        } catch (e) {
            categories = {};
        }
        await loadDay();
        loadHeatmap();
        finishBoot();
        wireEvents();
        tickClock();
        setInterval(tickClock, 1000);
        setInterval(() => { if (isToday()) loadDay(); }, REFRESH_MS);
    }

    function finishBoot() {
        if (booted) return;
        booted = true;
        const boot = document.getElementById('boot');
        boot.classList.add('out');
        const app = document.getElementById('app');
        app.hidden = false;
        setTimeout(() => { boot.hidden = true; }, 520);
    }

    // ── Data + rendering ─────────────────────────────────────────────────────

    async function loadDay() {
        const date = isoLocal(selected);
        updateDateLabel();
        try {
            const data = await getJSON(`/api/day/${date}`);
            lastDay = data;
            renderDay(data);
        } catch (e) {
            console.error('Failed to load day', e);
        }
    }

    async function loadHeatmap() {
        try {
            const data = await getJSON(`/api/heatmap?days=${HEATMAP_DAYS}`);
            const active = data.series.filter((d) => d.total_events > 0).length;
            document.getElementById('heatmap-meta').textContent =
                `Daily focus · last ${HEATMAP_DAYS} days · ${active} tracked`;
            ChronicleHeatmap.render(data.series, {
                selected: isoLocal(selected),
                onSelect: (iso) => {
                    const [y, m, d] = iso.split('-').map(Number);
                    selected = new Date(y, m - 1, d);
                    loadDay();
                    ChronicleHeatmap.setSelected(iso);
                    updateLivePill();
                },
            });
        } catch (e) {
            console.error('Failed to load heatmap', e);
        }
    }

    function renderDay(data) {
        const stats = data.stats || {};
        const hourly = data.hourly_entropy || {};

        // Score gauge + number + verdict.
        ChronicleCharts.renderGauge(data.focus_score || 0);
        CU.animateNumber(document.getElementById('score-value'), Math.round((data.focus_score || 0) * 100));
        const verdict = document.getElementById('score-verdict');
        const v = focusVerdict(data.focus_score || 0, data.total_events);
        verdict.textContent = v.label;
        verdict.style.color = v.color;

        ChronicleCharts.renderEntropySpark(hourly);

        // Headline metrics.
        const deepHours = Object.values(hourly).filter((h) => h.entropy < 0.34).length;
        setMetric('m-active', CU.formatHM(stats.active_seconds || 0));
        setMetric('m-productive', `${Math.round(stats.productive_pct || 0)}%`);
        setMetric('m-deepwork', String(deepHours));
        setMetric('m-longest', CU.formatHM((stats.longest_focus_minutes || 0) * 60));
        setMetric('m-switches', String(stats.context_switches || 0));
        setMetric('m-idle', CU.formatHM(stats.idle_seconds || 0));

        // Signature stream.
        ChronicleStream.render(data.timeline || [], { isToday: isToday(), categories });

        // Breakdown.
        ChronicleCharts.renderDonut(stats.top_categories || [], categories);
        ChronicleCharts.renderBars(stats.top_categories || [], categories);

        // Sessions.
        renderSessions(data.sessions || []);
        updateLivePill();
    }

    function setMetric(id, text) {
        document.getElementById(id).textContent = text;
    }

    function focusVerdict(score, events) {
        if (!events) return { label: 'No data yet', color: 'var(--fg-faint)' };
        const color = CU.focusColor(score);
        const pct = Math.round(score * 100); // keep verdict consistent with the shown number
        if (pct >= 70) return { label: 'Deep Focus', color };
        if (pct >= 55) return { label: 'Strong Focus', color };
        if (pct >= 40) return { label: 'Steady Focus', color };
        if (pct >= 25) return { label: 'Fragmented', color };
        return { label: 'Scattered', color };
    }

    function renderSessions(sessions) {
        const container = document.getElementById('sessions');
        const meta = document.getElementById('sessions-meta');
        container.innerHTML = '';
        if (!sessions.length) {
            container.innerHTML = '<div class="empty"><div class="empty-mark">◇</div>No focus sessions yet — they appear as activity is stitched together.</div>';
            meta.textContent = '';
            return;
        }
        meta.textContent = `${sessions.length} sessions`;

        let longestId = -1;
        let longest = 0;
        sessions.forEach((s, i) => {
            if (s.productive && s.duration_seconds > longest) { longest = s.duration_seconds; longestId = i; }
        });

        [...sessions].reverse().forEach((s) => {
            const originalIndex = sessions.indexOf(s);
            const row = document.createElement('div');
            row.className = 'session' + (originalIndex === longestId ? ' is-longest' : '');
            row.innerHTML = `
                <span class="session-accent" style="background:${s.color}"></span>
                <span class="session-icon">${s.icon || '•'}</span>
                <div class="session-body">
                    <div class="session-cat">${s.category}${originalIndex === longestId ? '<span class="session-tag">longest</span>' : ''}</div>
                    <div class="session-meta">${CU.clipTime(s.start_time)}–${CU.clipTime(s.end_time)} · ${s.app_name || 'unknown'}</div>
                </div>
                <div class="session-dur">
                    <div class="session-dur-val">${s.duration_formatted}</div>
                    <div class="session-dur-lbl">focus</div>
                </div>`;
            container.appendChild(row);
        });
    }

    // ── Navigation ───────────────────────────────────────────────────────────

    function navigate(deltaDays) {
        const next = new Date(selected);
        next.setDate(next.getDate() + deltaDays);
        if (next > new Date()) return;
        selected = next;
        loadDay();
        ChronicleHeatmap.setSelected(isoLocal(selected));
    }

    function goToday() {
        selected = new Date();
        loadDay();
        ChronicleHeatmap.setSelected(isoLocal(selected));
    }

    function updateDateLabel() {
        const label = document.getElementById('current-date');
        const sub = document.getElementById('current-sub');
        const today = new Date();
        const yesterday = new Date(today);
        yesterday.setDate(yesterday.getDate() - 1);

        if (sameDay(selected, today)) label.textContent = 'Today';
        else if (sameDay(selected, yesterday)) label.textContent = 'Yesterday';
        else label.textContent = selected.toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric' });

        sub.textContent = isoLocal(selected);
        document.getElementById('btn-next').disabled = sameDay(selected, today);
        document.getElementById('btn-today').style.visibility = sameDay(selected, today) ? 'hidden' : 'visible';
    }

    function updateLivePill() {
        document.getElementById('live-pill').style.display = isToday() ? 'flex' : 'none';
    }

    function exportDay() {
        const a = document.createElement('a');
        a.href = `/api/export/${isoLocal(selected)}?format=csv`;
        a.download = `chronicle-${isoLocal(selected)}.csv`;
        document.body.appendChild(a);
        a.click();
        a.remove();
    }

    function tickClock() {
        document.getElementById('clock').textContent =
            new Date().toLocaleTimeString('en-GB', { hour12: false });
    }

    function wireEvents() {
        document.getElementById('btn-prev').addEventListener('click', () => navigate(-1));
        document.getElementById('btn-next').addEventListener('click', () => navigate(1));
        document.getElementById('btn-today').addEventListener('click', goToday);
        document.getElementById('btn-export').addEventListener('click', exportDay);

        document.addEventListener('keydown', (e) => {
            if (e.target.tagName === 'INPUT') return;
            if (e.key === 'ArrowLeft') navigate(-1);
            else if (e.key === 'ArrowRight') navigate(1);
            else if (e.key === 't' || e.key === 'T') goToday();
        });

        const redraw = CU.debounce(() => {
            ChronicleStream.redraw();
            if (lastDay) ChronicleCharts.renderEntropySpark(lastDay.hourly_entropy || {});
        }, 150);
        window.addEventListener('resize', redraw);

        // Redraw the width-dependent stream once layout settles — covers the
        // case where the first render happened before the panel had a width.
        if (window.ResizeObserver) {
            const streamEl = document.getElementById('stream');
            let lastW = streamEl.clientWidth;
            new ResizeObserver(() => {
                if (Math.abs(streamEl.clientWidth - lastW) > 2) {
                    lastW = streamEl.clientWidth;
                    redraw();
                }
            }).observe(streamEl);
        }
    }

    return { init };
})();

document.addEventListener('DOMContentLoaded', () => ChronicleApp.init());
