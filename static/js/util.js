/**
 * Chronicle — shared helpers.
 * Formatting, the focus-spectrum colour scale, and a single shared tooltip.
 */
const CU = (() => {
    // Focus spectrum: 0 (scattered) → 1 (deep focus), threaded through every chart.
    const focusScale = d3.scaleLinear()
        .domain([0, 0.5, 1])
        .range(['#fb6f84', '#f5b945', '#2dd4bf'])
        .clamp(true);

    /** Colour for a focus score (0–1): rose → amber → teal. */
    const focusColor = (score) => focusScale(score);

    /** Colour for an entropy value (0–1): the inverse of the focus scale. */
    const entropyColor = (entropy) => focusScale(1 - entropy);

    /** "1h 5m" / "12m" / "40s" from a second count. */
    function formatDuration(seconds) {
        seconds = Math.round(seconds || 0);
        if (seconds < 60) return `${seconds}s`;
        if (seconds < 3600) {
            const m = Math.floor(seconds / 60);
            const s = seconds % 60;
            return s ? `${m}m ${s}s` : `${m}m`;
        }
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        return m ? `${h}h ${m}m` : `${h}h`;
    }

    /** Compact "Xh Ym" / "Ym" for headline metrics. */
    function formatHM(seconds) {
        seconds = Math.round(seconds || 0);
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        if (h && m) return `${h}h ${m}m`;
        if (h) return `${h}h`;
        return `${m}m`;
    }

    /** Minute-of-day (0–1439) → "HH:MM". */
    function minuteToTime(minute) {
        const h = Math.floor(minute / 60);
        const m = minute % 60;
        return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
    }

    /** "HH:MM" from a "YYYY-MM-DD HH:MM:SS" timestamp. */
    const clipTime = (ts) => (ts && ts.length >= 16 ? ts.slice(11, 16) : ts || '');

    function hexToRgba(hex, alpha) {
        const v = hex.replace('#', '');
        const r = parseInt(v.slice(0, 2), 16);
        const g = parseInt(v.slice(2, 4), 16);
        const b = parseInt(v.slice(4, 6), 16);
        return `rgba(${r}, ${g}, ${b}, ${alpha})`;
    }

    function debounce(fn, wait) {
        let t;
        return (...args) => {
            clearTimeout(t);
            t = setTimeout(() => fn(...args), wait);
        };
    }

    /**
     * Whether to animate. We skip animation when the user prefers reduced
     * motion or the page isn't visible — in a hidden/headless tab rAF is
     * throttled, so animating there would leave charts stuck at their initial
     * frame. Callers must always render a correct *final* state.
     */
    function shouldAnimate() {
        if (document.hidden) return false;
        if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return false;
        // ?static renders everything in its final state (used for screenshots).
        if (new URLSearchParams(location.search).has('static')) return false;
        return true;
    }

    /** Ease a number from 0 to a target, or set it directly when not animating. */
    function animateNumber(el, target, { duration = 900, format = (v) => Math.round(v) } = {}) {
        if (!shouldAnimate()) { el.textContent = format(target); return; }
        const start = performance.now();
        function frame(now) {
            const t = Math.min(1, (now - start) / duration);
            const eased = 1 - Math.pow(1 - t, 3);
            el.textContent = format(target * eased);
            if (t < 1) requestAnimationFrame(frame);
            else el.textContent = format(target);
        }
        requestAnimationFrame(frame);
    }

    // ── Shared tooltip ──────────────────────────────────────────────────────
    const tip = {
        el: null,
        node() {
            if (!this.el) this.el = document.getElementById('tooltip');
            return this.el;
        },
        show(html, event) {
            const n = this.node();
            n.innerHTML = html;
            n.hidden = false;
            this.move(event);
        },
        move(event) {
            const n = this.node();
            const pad = 14;
            let x = event.clientX + pad;
            let y = event.clientY + pad;
            const r = n.getBoundingClientRect();
            if (x + r.width > window.innerWidth) x = event.clientX - r.width - pad;
            if (y + r.height > window.innerHeight) y = event.clientY - r.height - pad;
            n.style.left = `${x}px`;
            n.style.top = `${y}px`;
        },
        hide() {
            this.node().hidden = true;
        },
    };

    return {
        focusColor, entropyColor, focusScale,
        formatDuration, formatHM, minuteToTime, clipTime,
        hexToRgba, debounce, animateNumber, shouldAnimate, tip,
    };
})();
