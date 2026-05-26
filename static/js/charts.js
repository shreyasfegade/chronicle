/**
 * Chronicle — D3 Charts
 * Entropy bar chart, category donut chart, and category bar breakdown.
 */

const ChronicleCharts = (() => {

    /**
     * Render the hourly entropy bar chart.
     * Each bar represents one hour's focus entropy (0 = focused, 1 = fragmented).
     */
    function renderEntropyChart(hourlyEntropy) {
        const container = document.getElementById('entropy-chart');
        if (!container) return;
        container.innerHTML = '';

        const width = container.clientWidth;
        const height = container.clientHeight || 140;
        const margin = { top: 10, right: 10, bottom: 24, left: 10 };
        const innerW = width - margin.left - margin.right;
        const innerH = height - margin.top - margin.bottom;

        const svg = d3.select(container)
            .append('svg')
            .attr('width', width)
            .attr('height', height);

        const g = svg.append('g')
            .attr('transform', `translate(${margin.left},${margin.top})`);

        // Prepare data for all 24 hours
        const data = [];
        for (let h = 0; h < 24; h++) {
            const key = h.toString();
            const info = hourlyEntropy[key];
            data.push({
                hour: h,
                entropy: info ? info.entropy : 0,
                hasData: !!info,
                totalEvents: info ? info.total_events : 0,
                dominant: info ? info.dominant_category : null,
            });
        }

        const x = d3.scaleBand()
            .domain(data.map(d => d.hour))
            .range([0, innerW])
            .padding(0.3);

        const y = d3.scaleLinear()
            .domain([0, 1])
            .range([innerH, 0]);

        // Gradient for entropy bars
        const defs = svg.append('defs');

        // Low entropy = green (focused), high = red (fragmented)
        function getBarColor(entropy) {
            if (entropy <= 0.3) return '#10b981';
            if (entropy <= 0.5) return '#6366f1';
            if (entropy <= 0.7) return '#f59e0b';
            return '#f43f5e';
        }

        function getBarOpacity(entropy, hasData) {
            if (!hasData) return 0.05;
            return 0.7 + entropy * 0.3;
        }

        // Background guide lines
        [0.25, 0.5, 0.75].forEach(val => {
            g.append('line')
                .attr('x1', 0)
                .attr('x2', innerW)
                .attr('y1', y(val))
                .attr('y2', y(val))
                .attr('stroke', 'rgba(255,255,255,0.04)')
                .attr('stroke-dasharray', '3,3');
        });

        // Focus zone label
        g.append('text')
            .attr('x', innerW - 4)
            .attr('y', y(0.15))
            .attr('text-anchor', 'end')
            .attr('fill', 'rgba(16, 185, 129, 0.3)')
            .attr('font-size', '9px')
            .attr('font-family', 'Inter, sans-serif')
            .text('FOCUSED');

        g.append('text')
            .attr('x', innerW - 4)
            .attr('y', y(0.85))
            .attr('text-anchor', 'end')
            .attr('fill', 'rgba(244, 63, 94, 0.3)')
            .attr('font-size', '9px')
            .attr('font-family', 'Inter, sans-serif')
            .text('SCATTERED');

        // Bars
        g.selectAll('.entropy-bar')
            .data(data)
            .enter()
            .append('rect')
            .attr('class', 'entropy-bar')
            .attr('x', d => x(d.hour))
            .attr('width', x.bandwidth())
            .attr('y', d => d.hasData ? y(Math.max(d.entropy, 0.03)) : y(0.03))
            .attr('height', d => d.hasData ? innerH - y(Math.max(d.entropy, 0.03)) : innerH - y(0.03))
            .attr('rx', 3)
            .attr('fill', d => d.hasData ? getBarColor(d.entropy) : 'rgba(255,255,255,0.03)')
            .attr('opacity', d => getBarOpacity(d.entropy, d.hasData));

        // Hour labels
        g.selectAll('.hour-label')
            .data(data)
            .enter()
            .append('text')
            .attr('x', d => x(d.hour) + x.bandwidth() / 2)
            .attr('y', innerH + 16)
            .attr('text-anchor', 'middle')
            .attr('fill', d => d.hasData ? 'rgba(240,240,245,0.4)' : 'rgba(240,240,245,0.15)')
            .attr('font-size', '9px')
            .attr('font-family', 'Inter, sans-serif')
            .attr('font-variant-numeric', 'tabular-nums')
            .text(d => d.hour % 2 === 0 ? d.hour.toString().padStart(2, '0') : '');

        // Trigger animation
        ChronicleAnimations.animateEntropyBars();
    }

    /**
     * Render the category donut chart.
     */
    function renderCategoryDonut(topCategories, categories) {
        const container = document.getElementById('category-donut');
        if (!container) return;
        container.innerHTML = '';

        const size = Math.min(container.clientWidth, container.clientHeight) || 200;
        const radius = size / 2;
        const innerRadius = radius * 0.6;

        const svg = d3.select(container)
            .append('svg')
            .attr('width', size)
            .attr('height', size)
            .append('g')
            .attr('transform', `translate(${radius},${radius})`);

        if (!topCategories || topCategories.length === 0) {
            svg.append('text')
                .attr('text-anchor', 'middle')
                .attr('dy', '0.35em')
                .attr('fill', 'rgba(240,240,245,0.2)')
                .attr('font-size', '13px')
                .attr('font-family', 'Inter, sans-serif')
                .text('No data');
            return;
        }

        // Filter out tiny categories for cleaner chart
        const filtered = topCategories.filter(c => c.percentage > 1);

        const pie = d3.pie()
            .value(d => d.seconds)
            .sort(null)
            .padAngle(0.03);

        const arc = d3.arc()
            .innerRadius(innerRadius)
            .outerRadius(radius - 4)
            .cornerRadius(4);

        const arcHover = d3.arc()
            .innerRadius(innerRadius)
            .outerRadius(radius)
            .cornerRadius(4);

        const arcs = svg.selectAll('.donut-arc')
            .data(pie(filtered))
            .enter()
            .append('path')
            .attr('class', 'donut-arc')
            .attr('d', arc)
            .attr('fill', d => {
                const catInfo = categories[d.data.category];
                return catInfo ? catInfo.color : '#6b7280';
            })
            .attr('opacity', 0.85)
            .style('cursor', 'pointer')
            .style('transition', 'opacity 0.2s');

        // Hover effect
        arcs.on('mouseenter', function (event, d) {
            d3.select(this)
                .transition()
                .duration(200)
                .attr('d', arcHover)
                .attr('opacity', 1);

            // Update center text
            centerValue.text(d.data.percentage + '%');
            centerLabel.text(d.data.category);
        })
        .on('mouseleave', function () {
            d3.select(this)
                .transition()
                .duration(200)
                .attr('d', arc)
                .attr('opacity', 0.85);

            // Reset center text
            const totalSeconds = topCategories.reduce((s, c) => s + c.seconds, 0);
            centerValue.text(formatHours(totalSeconds));
            centerLabel.text('Total');
        });

        // Entrance animation
        arcs.attr('opacity', 0)
            .transition()
            .duration(800)
            .delay((d, i) => i * 80)
            .attr('opacity', 0.85)
            .attrTween('d', function (d) {
                const interpolate = d3.interpolate(
                    { startAngle: d.startAngle, endAngle: d.startAngle },
                    d
                );
                return t => arc(interpolate(t));
            });

        // Center text
        const totalSeconds = topCategories.reduce((s, c) => s + c.seconds, 0);

        const centerValue = svg.append('text')
            .attr('class', 'donut-center-value')
            .attr('text-anchor', 'middle')
            .attr('dy', '-0.1em')
            .text(formatHours(totalSeconds));

        const centerLabel = svg.append('text')
            .attr('class', 'donut-center-label')
            .attr('text-anchor', 'middle')
            .attr('dy', '1.4em')
            .text('Total');
    }

    /**
     * Render the category bar breakdown.
     */
    function renderCategoryBars(topCategories, categories) {
        const container = document.getElementById('category-bars');
        if (!container) return;
        container.innerHTML = '';

        if (!topCategories || topCategories.length === 0) {
            container.innerHTML = `
                <div class="empty-state" style="padding: 30px 10px;">
                    <div class="empty-state-text">No activity categories yet</div>
                </div>`;
            return;
        }

        const maxSeconds = Math.max(...topCategories.map(c => c.seconds));

        topCategories.forEach(cat => {
            const catInfo = categories[cat.category] || { color: '#6b7280', icon: '❓' };
            const barWidth = maxSeconds > 0 ? (cat.seconds / maxSeconds) * 100 : 0;

            const item = document.createElement('div');
            item.className = 'category-bar-item';
            item.innerHTML = `
                <span class="category-bar-icon">${catInfo.icon}</span>
                <span class="category-bar-name">${cat.category}</span>
                <div class="category-bar-track">
                    <div class="category-bar-fill" data-width="${barWidth}%"
                         style="background: ${catInfo.color};"></div>
                </div>
                <span class="category-bar-value">${formatDuration(cat.seconds)}</span>
            `;
            container.appendChild(item);
        });

        // Trigger animation
        ChronicleAnimations.animateCategoryBars();
    }

    // ── Utility functions ──────────────────────────────────────────────

    function formatDuration(seconds) {
        if (seconds < 60) return `${Math.round(seconds)}s`;
        if (seconds < 3600) {
            const m = Math.floor(seconds / 60);
            return `${m}m`;
        }
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        return m > 0 ? `${h}h ${m}m` : `${h}h`;
    }

    function formatHours(seconds) {
        if (seconds < 3600) {
            const m = Math.floor(seconds / 60);
            return `${m}m`;
        }
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        return m > 0 ? `${h}h ${m}m` : `${h}h`;
    }

    return {
        renderEntropyChart,
        renderCategoryDonut,
        renderCategoryBars,
    };
})();
