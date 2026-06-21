/**
 * Chronicle — Focus Stream (the signature visualization).
 *
 * The whole day is drawn as one flowing ribbon along a 24-hour axis:
 *   • horizontal position  → time of day
 *   • colour               → activity category
 *   • thickness            → how active you were (idle thins the ribbon)
 *   • edge turbulence       → entropy: focused hours render as calm, smooth
 *                             water; fragmented hours fray into choppy noise.
 *
 * Everything is hand-built from D3 path geometry — no chart component, no plugin.
 * The turbulence is a small sum-of-sines noise field whose amplitude is scaled
 * by each moment's entropy, so the metric is something you *see*, not a number.
 */
const ChronicleStream = (() => {
    const MINUTES = 1440;
    const SAMPLE_STEP = 0.5;     // minutes between path samples (sub-minute = smooth fray)
    const GAP_MINUTES = 3;       // a gap longer than this breaks the ribbon

    let lastData = null;

    /** Deterministic pseudo-noise in [-1, 1] from layered sines. */
    function noise(x, phase) {
        return (
            Math.sin(x * 0.85 + phase) * 0.5 +
            Math.sin(x * 2.3 + phase * 1.7) * 0.32 +
            Math.sin(x * 5.4 + phase * 0.6) * 0.18
        );
    }

    /** Split the minute buckets into contiguous same-category runs. */
    function buildSegments(timeline) {
        const byMinute = new Map(timeline.map((d) => [d.minute, d]));
        const segments = [];
        let current = null;
        const sorted = [...timeline].sort((a, b) => a.minute - b.minute);

        for (const d of sorted) {
            const breaks =
                !current ||
                d.category !== current.category ||
                d.minute - current.lastMinute > GAP_MINUTES;
            if (breaks) {
                current = { category: d.category, color: d.color, points: [], lastMinute: d.minute };
                segments.push(current);
            }
            current.points.push(d);
            current.lastMinute = d.minute;
        }
        return segments;
    }

    function render(timeline, opts = {}) {
        lastData = { timeline, opts };
        const container = document.getElementById('stream');
        const axisEl = document.getElementById('stream-axis');
        container.innerHTML = '';
        axisEl.innerHTML = '';

        // Guard against being called before layout has settled (e.g. a hidden
        // tab or a not-yet-flushed first paint), where clientWidth can be 0.
        const width = container.clientWidth
            || container.getBoundingClientRect().width
            || (container.parentElement && container.parentElement.clientWidth)
            || 960;
        const height = container.clientHeight || 180;
        const x = d3.scaleLinear().domain([0, MINUTES]).range([0, width]);

        const svg = d3.select(container).append('svg').attr('viewBox', `0 0 ${width} ${height}`);

        if (!timeline || timeline.length === 0) {
            svg.append('text')
                .attr('x', width / 2).attr('y', height / 2)
                .attr('text-anchor', 'middle').attr('fill', 'var(--fg-faint)')
                .attr('font-size', 13)
                .text('No activity recorded for this day yet.');
            renderAxis(axisEl, x, width);
            return;
        }

        const midY = height * 0.5;
        const maxHalf = height * 0.19;
        const maxTurb = height * 0.14;

        // Hour gridlines behind the ribbon.
        const grid = svg.append('g');
        for (let h = 0; h <= 24; h += 1) {
            grid.append('line')
                .attr('x1', x(h * 60)).attr('x2', x(h * 60))
                .attr('y1', 6).attr('y2', height - 6)
                .attr('stroke', 'var(--line)')
                .attr('stroke-width', h % 6 === 0 ? 1 : 0.5)
                .attr('opacity', h % 6 === 0 ? 0.9 : 0.4);
        }
        grid.append('line')
            .attr('x1', 0).attr('x2', width).attr('y1', midY).attr('y2', midY)
            .attr('stroke', 'var(--line)').attr('opacity', 0.5);

        const ribbons = svg.append('g').attr('class', 'ribbons');

        buildSegments(timeline).forEach((seg, i) => {
            if (seg.points.length === 0) return;
            const m0 = seg.points[0].minute;
            const m1 = seg.lastMinute + 1;
            const lookup = new Map(seg.points.map((p) => [p.minute, p]));

            const sample = (m) => lookup.get(Math.round(m)) || seg.points[seg.points.length - 1];
            const tops = [];
            const bots = [];
            for (let m = m0; m <= m1; m += SAMPLE_STEP) {
                const p = sample(m);
                const half = maxHalf * (0.22 + 0.78 * (p.active_ratio ?? 1));
                const turb = maxTurb * (p.entropy ?? 0);
                const px = x(m);
                tops.push([px, midY - half + turb * noise(m, 0.0)]);
                bots.push([px, midY + half - turb * noise(m, 3.1)]);
            }

            const line = d3.line().curve(d3.curveBasis);
            const path = `${line(tops)}L${bots.slice().reverse().map((d) => d.join(',')).join('L')}Z`;

            const ribbon = ribbons.append('path')
                .attr('d', path)
                .attr('fill', seg.color)
                .attr('fill-opacity', 0.82)
                .attr('stroke', seg.color)
                .attr('stroke-width', 0.6)
                .attr('stroke-opacity', 0.55);

            // Entrance: wipe in from the flat midline (skipped when not animating,
            // so a hidden/headless render still shows the finished ribbon).
            if (CU.shouldAnimate()) {
                const flat = `${line(tops.map((d) => [d[0], midY]))}L${bots.map((d) => [d[0], midY]).reverse().map((d) => d.join(',')).join('L')}Z`;
                ribbon.attr('d', flat).transition().duration(700).delay(i * 12).ease(d3.easeCubicOut).attr('d', path);
            }
        });

        // "Now" marker when viewing today.
        if (opts.isToday) {
            const now = new Date();
            const nowMin = now.getHours() * 60 + now.getMinutes();
            const nx = x(nowMin);
            svg.append('line').attr('x1', nx).attr('x2', nx).attr('y1', 0).attr('y2', height)
                .attr('stroke', 'var(--fg)').attr('stroke-width', 1).attr('opacity', 0.55);
            svg.append('circle').attr('cx', nx).attr('cy', 0).attr('r', 3).attr('fill', 'var(--fg)');
        }

        attachScrubber(svg, container, x, width, height, timeline);
        renderAxis(axisEl, x, width);
        renderLegend(timeline, opts.categories || {});
    }

    function attachScrubber(svg, container, x, width, height, timeline) {
        const byMinute = new Map(timeline.map((d) => [d.minute, d]));
        const minutes = timeline.map((d) => d.minute).sort((a, b) => a - b);
        const scrub = svg.append('line').attr('class', 'stream-scrubber')
            .attr('y1', 0).attr('y2', height).attr('opacity', 0);

        svg.append('rect')
            .attr('width', width).attr('height', height).attr('fill', 'transparent')
            .style('cursor', 'crosshair')
            .on('mousemove', function (event) {
                const [mx] = d3.pointer(event);
                const minute = Math.round(x.invert(mx));
                // Snap to the nearest minute that actually has data.
                let nearest = null, best = Infinity;
                for (const m of minutes) {
                    const dist = Math.abs(m - minute);
                    if (dist < best) { best = dist; nearest = m; }
                }
                if (nearest === null || best > 8) { scrub.attr('opacity', 0); CU.tip.hide(); return; }
                const d = byMinute.get(nearest);
                scrub.attr('x1', x(nearest)).attr('x2', x(nearest)).attr('opacity', 1);
                const focused = d.entropy < 0.34 ? 'deep focus' : d.entropy < 0.66 ? 'mixed' : 'scattered';
                CU.tip.show(
                    `<div class="tt-time">${CU.minuteToTime(nearest)}</div>
                     <div class="tt-row"><span class="tt-dot" style="background:${d.color}"></span>${d.category}</div>
                     ${d.app ? `<div class="tt-sub">${d.app}</div>` : ''}
                     <div class="tt-sub">active <span class="tt-metric">${Math.round((d.active_ratio ?? 1) * 100)}%</span> · entropy <span class="tt-metric">${d.entropy.toFixed(2)}</span> (${focused})</div>`,
                    event,
                );
            })
            .on('mouseleave', () => { scrub.attr('opacity', 0); CU.tip.hide(); });
    }

    function renderAxis(axisEl, x, width) {
        const svg = d3.select(axisEl).append('svg')
            .attr('viewBox', `0 0 ${width} 22`).attr('width', '100%').attr('height', 22);
        for (let h = 0; h <= 24; h += 3) {
            svg.append('text').attr('class', 'axis-tick')
                .attr('x', Math.min(width - 14, Math.max(8, x(h * 60))))
                .attr('y', 14).attr('text-anchor', 'middle')
                .text(`${String(h % 24).padStart(2, '0')}:00`);
        }
    }

    function renderLegend(timeline, categories) {
        const el = document.getElementById('stream-legend');
        if (!el) return;
        const seen = [];
        const present = new Set();
        for (const d of timeline) {
            if (!present.has(d.category)) { present.add(d.category); seen.push(d); }
        }
        el.innerHTML = seen
            .filter((d) => d.category !== 'Idle')
            .map((d) => `<span class="legend-item"><span class="legend-swatch" style="background:${d.color}"></span>${d.category}</span>`)
            .join('');
    }

    function redraw() {
        if (lastData) render(lastData.timeline, lastData.opts);
    }

    return { render, redraw };
})();
