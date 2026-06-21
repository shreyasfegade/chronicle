/**
 * Chronicle — Focus Rhythm heatmap.
 * A calendar grid (weeks × weekdays) where each cell is a day, coloured by its
 * Focus Score along the shared focus spectrum. Clicking a day navigates the
 * dashboard to it, so the heatmap doubles as a date picker.
 */
const ChronicleHeatmap = (() => {
    const CELL = 13;
    const GAP = 3;
    const TOP = 16;     // room for month labels
    const LEFT = 22;    // room for weekday labels

    let onSelect = null;
    let selectedDate = null;

    const parseDate = (s) => {
        const [y, m, d] = s.split('-').map(Number);
        return new Date(y, m - 1, d);
    };
    const isoOf = (date) => {
        const y = date.getFullYear();
        const m = String(date.getMonth() + 1).padStart(2, '0');
        const d = String(date.getDate()).padStart(2, '0');
        return `${y}-${m}-${d}`;
    };
    const mondayIndex = (date) => (date.getDay() + 6) % 7; // Mon=0 … Sun=6

    function setSelected(dateStr) {
        selectedDate = dateStr;
        d3.selectAll('.heat-cell').classed('selected', function () {
            return this.getAttribute('data-date') === dateStr;
        });
    }

    function render(series, opts = {}) {
        onSelect = opts.onSelect || null;
        selectedDate = opts.selected || null;
        const container = document.getElementById('heatmap');
        container.innerHTML = '';
        if (!series || series.length === 0) return;

        const byDate = new Map(series.map((d) => [d.date, d]));
        const start = parseDate(series[0].date);
        const end = parseDate(series[series.length - 1].date);

        // Column 0 begins on the Monday of the first week.
        const gridStart = new Date(start);
        gridStart.setDate(gridStart.getDate() - mondayIndex(start));
        const weeks = Math.ceil((((end - gridStart) / 86400000) + 1) / 7);

        const width = LEFT + weeks * (CELL + GAP);
        const height = TOP + 7 * (CELL + GAP);
        const svg = d3.select(container).append('svg')
            .attr('viewBox', `0 0 ${width} ${height}`)
            .attr('width', width).attr('height', height);

        // Weekday labels (Mon / Wed / Fri).
        ['Mon', '', 'Wed', '', 'Fri', '', ''].forEach((label, row) => {
            if (!label) return;
            svg.append('text').attr('class', 'heat-day-label')
                .attr('x', 0).attr('y', TOP + row * (CELL + GAP) + CELL - 2)
                .text(label);
        });

        const monthsSeen = new Set();
        const today = isoOf(new Date());

        for (let i = 0; ; i += 1) {
            const date = new Date(gridStart);
            date.setDate(date.getDate() + i);
            if (date > end) break;

            const col = Math.floor(i / 7);
            const row = mondayIndex(date);
            const cx = LEFT + col * (CELL + GAP);
            const cy = TOP + row * (CELL + GAP);
            const iso = isoOf(date);

            // Month label at the first column a month appears in.
            const monthKey = `${date.getFullYear()}-${date.getMonth()}`;
            if (date.getDate() <= 7 && !monthsSeen.has(monthKey)) {
                monthsSeen.add(monthKey);
                svg.append('text').attr('class', 'heat-month-label')
                    .attr('x', cx).attr('y', 10)
                    .text(date.toLocaleString('en-US', { month: 'short' }));
            }

            const datum = byDate.get(iso);
            const hasData = datum && datum.total_events > 0;
            const inRange = date >= start && date <= end;
            const fill = hasData ? CU.focusColor(datum.focus_score) : 'rgba(255,255,255,0.04)';

            const cell = svg.append('rect')
                .attr('class', 'heat-cell')
                .attr('data-date', iso)
                .attr('x', cx).attr('y', cy)
                .attr('width', CELL).attr('height', CELL)
                .attr('rx', 2.5)
                .attr('fill', inRange ? fill : 'transparent')
                .attr('opacity', hasData ? 0.92 : 0.6)
                .classed('selected', iso === selectedDate);

            if (!inRange) { cell.style('pointer-events', 'none'); continue; }

            cell.on('click', () => { if (onSelect && date <= new Date()) onSelect(iso); })
                .on('mouseenter', (event) => {
                    const label = date.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
                    const body = hasData
                        ? `<div class="tt-sub">focus <span class="tt-metric">${Math.round(datum.focus_score * 100)}</span> · active <span class="tt-metric">${CU.formatHM(datum.active_seconds)}</span></div>`
                        : `<div class="tt-sub">no data${iso === today ? ' yet' : ''}</div>`;
                    CU.tip.show(`<div class="tt-time">${label}</div>${body}`, event);
                })
                .on('mousemove', (event) => CU.tip.move(event))
                .on('mouseleave', () => CU.tip.hide());
        }

        // Gradient key under the grid.
        const key = document.getElementById('heatmap-scale');
        if (key) {
            const stops = d3.range(0, 1.01, 0.1).map((t) => CU.focusColor(t)).join(', ');
            key.style.background = `linear-gradient(90deg, ${stops})`;
        }
    }

    return { render, setSelected };
})();
