/**
 * Chronicle — supporting D3 charts: the focus gauge, the entropy sparkline,
 * the category donut, and the ranked category bars. All hand-built; the focus
 * spectrum (see util.js) ties their colours to the Focus Stream.
 */
const ChronicleCharts = (() => {
    const TAU = Math.PI * 2;
    const GAUGE_SWEEP = (270 * Math.PI) / 180; // 270° arc with a gap at the bottom
    const GAUGE_START = -GAUGE_SWEEP / 2;

    /** 270° focus gauge. The numeric value is the HTML overlay; this is the arc. */
    function renderGauge(score) {
        const container = document.getElementById('focus-gauge');
        container.innerHTML = '';
        const size = 180;
        const r = 78;
        const svg = d3.select(container).append('svg')
            .attr('viewBox', `0 0 ${size} ${size}`).attr('width', size).attr('height', size);
        const g = svg.append('g').attr('transform', `translate(${size / 2},${size / 2})`);

        const track = d3.arc().innerRadius(r - 9).outerRadius(r)
            .startAngle(GAUGE_START).endAngle(GAUGE_START + GAUGE_SWEEP).cornerRadius(6);
        g.append('path').attr('d', track).attr('fill', 'rgba(255,255,255,0.06)');

        // Tick marks around the arc.
        const ticks = 28;
        for (let i = 0; i <= ticks; i += 1) {
            const a = GAUGE_START + (i / ticks) * GAUGE_SWEEP - Math.PI / 2;
            const on = i / ticks <= score;
            g.append('line')
                .attr('x1', Math.cos(a) * (r + 4)).attr('y1', Math.sin(a) * (r + 4))
                .attr('x2', Math.cos(a) * (r + 8)).attr('y2', Math.sin(a) * (r + 8))
                .attr('stroke', on ? CU.focusColor(score) : 'rgba(255,255,255,0.08)')
                .attr('stroke-width', 1.5).attr('opacity', on ? 0.9 : 1);
        }

        const value = d3.arc().innerRadius(r - 9).outerRadius(r)
            .startAngle(GAUGE_START).cornerRadius(6);
        const path = g.append('path')
            .attr('fill', CU.focusColor(score))
            .style('filter', `drop-shadow(0 0 6px ${CU.hexToRgba(CU.focusColor(score), 0.5)})`)
            .attr('d', value.endAngle(GAUGE_START + score * GAUGE_SWEEP)());

        // Animate the arc sweeping to its value (final state already set above).
        if (CU.shouldAnimate()) {
            path.transition().duration(1100).ease(d3.easeCubicOut)
                .attrTween('d', () => {
                    const end = d3.interpolate(GAUGE_START, GAUGE_START + score * GAUGE_SWEEP);
                    return (t) => value.endAngle(end(t))();
                });
        }
    }

    /** Tiny per-hour entropy sparkline — a miniature echo of the stream's fray. */
    function renderEntropySpark(hourly) {
        const container = document.getElementById('entropy-spark');
        container.innerHTML = '';
        const width = container.clientWidth || 280;
        const height = 38;
        const svg = d3.select(container).append('svg')
            .attr('viewBox', `0 0 ${width} ${height}`).attr('width', '100%').attr('height', height);

        const x = d3.scaleBand().domain(d3.range(24)).range([0, width]).padding(0.28);
        for (let h = 0; h < 24; h += 1) {
            const info = hourly[String(h)];
            const has = !!info;
            const e = has ? info.entropy : 0;
            const barH = has ? Math.max(2, e * height) : 2;
            svg.append('rect')
                .attr('x', x(h)).attr('width', x.bandwidth())
                .attr('y', height - barH).attr('height', barH).attr('rx', 1.5)
                .attr('fill', has ? CU.entropyColor(e) : 'rgba(255,255,255,0.06)')
                .attr('opacity', has ? 0.9 : 1)
                .on('mouseenter', (event) => {
                    if (!has) return;
                    CU.tip.show(`<div class="tt-time">${String(h).padStart(2, '0')}:00</div><div class="tt-sub">entropy <span class="tt-metric">${e.toFixed(2)}</span> · ${info.dominant_category}</div>`, event);
                })
                .on('mousemove', (event) => CU.tip.move(event))
                .on('mouseleave', () => CU.tip.hide());
        }
    }

    /** Category donut with a live centre readout. */
    function renderDonut(topCategories, categories) {
        const container = document.getElementById('donut');
        container.innerHTML = '';
        const size = 190;
        const r = size / 2;
        const svg = d3.select(container).append('svg')
            .attr('viewBox', `0 0 ${size} ${size}`).attr('width', size).attr('height', size)
            .append('g').attr('transform', `translate(${r},${r})`);

        const data = (topCategories || []).filter((c) => c.category !== 'Idle' && c.percentage >= 1);
        if (data.length === 0) {
            svg.append('text').attr('text-anchor', 'middle').attr('dy', '0.35em')
                .attr('fill', 'var(--fg-faint)').attr('font-size', 12).text('No data');
            return;
        }

        const totalActive = data.reduce((s, c) => s + c.seconds, 0);
        const pie = d3.pie().value((d) => d.seconds).sort(null).padAngle(0.02);
        const arc = d3.arc().innerRadius(r * 0.62).outerRadius(r - 3).cornerRadius(3);
        const arcHover = d3.arc().innerRadius(r * 0.62).outerRadius(r).cornerRadius(3);

        const centerVal = svg.append('text').attr('class', 'donut-total')
            .attr('text-anchor', 'middle').attr('dy', '-0.05em').text(CU.formatHM(totalActive));
        const centerLbl = svg.append('text').attr('class', 'donut-label')
            .attr('text-anchor', 'middle').attr('dy', '1.5em').text('ACTIVE');

        const arcs = svg.selectAll('path').data(pie(data)).enter().append('path')
            .attr('d', arc)
            .attr('fill', (d) => (categories[d.data.category] || {}).color || '#6b7280')
            .attr('opacity', 0.9).style('cursor', 'pointer')
            .on('mouseenter', function (event, d) {
                d3.select(this).transition().duration(150).attr('d', arcHover).attr('opacity', 1);
                centerVal.text(`${d.data.percentage}%`);
                centerLbl.text(d.data.category.toUpperCase());
            })
            .on('mouseleave', function () {
                d3.select(this).transition().duration(150).attr('d', arc).attr('opacity', 0.9);
                centerVal.text(CU.formatHM(totalActive));
                centerLbl.text('ACTIVE');
            });

        if (CU.shouldAnimate()) {
            arcs.transition().duration(800).delay((d, i) => i * 60)
                .attrTween('d', (d) => {
                    const i = d3.interpolate({ startAngle: d.startAngle, endAngle: d.startAngle }, d);
                    return (t) => arc(i(t));
                });
        }
    }

    /** Ranked category bars with productive/distracting tinting. */
    function renderBars(topCategories, categories) {
        const container = document.getElementById('bars');
        container.innerHTML = '';
        const data = (topCategories || []).filter((c) => c.seconds > 0 && c.category !== 'Idle').slice(0, 8);
        if (data.length === 0) {
            container.innerHTML = '<div class="empty">No activity categories yet.</div>';
            return;
        }
        const max = d3.max(data, (c) => c.seconds);
        data.forEach((cat) => {
            const info = categories[cat.category] || { color: '#6b7280' };
            const row = document.createElement('div');
            row.className = 'bar-row';
            row.innerHTML = `
                <span class="bar-dot" style="background:${info.color}"></span>
                <div class="bar-main">
                    <div class="bar-name"><span>${cat.category}</span><span class="bar-pct">${cat.percentage}%</span></div>
                    <div class="bar-track"><div class="bar-fill" style="background:${info.color}"></div></div>
                </div>
                <span class="bar-time">${CU.formatDuration(cat.seconds)}</span>`;
            container.appendChild(row);
            const fill = row.querySelector('.bar-fill');
            const pct = `${(cat.seconds / max) * 100}%`;
            if (CU.shouldAnimate()) requestAnimationFrame(() => { fill.style.width = pct; });
            else fill.style.width = pct;
        });
    }

    return { renderGauge, renderEntropySpark, renderDonut, renderBars };
})();
