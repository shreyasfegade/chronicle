/**
 * Chronicle — D3 Horizontal Timeline
 * Renders a beautiful horizontal timeline bar where each minute is colored
 * by the dominant activity category. Shows current time indicator.
 */

const ChronicleTimeline = (() => {
    let tooltipEl = null;

    function init() {
        tooltipEl = document.getElementById('timeline-tooltip');
        renderHourLabels();
    }

    function renderHourLabels() {
        const container = document.getElementById('timeline-hours');
        if (!container) return;
        container.innerHTML = '';
        for (let h = 0; h <= 23; h += 1) {
            const span = document.createElement('span');
            // Show label every 2 hours, show dot for odd hours
            if (h % 2 === 0) {
                span.textContent = h.toString().padStart(2, '0');
            } else {
                span.textContent = '·';
                span.style.opacity = '0.3';
            }
            container.appendChild(span);
        }
    }

    /**
     * Render the timeline from API data.
     * @param {Array} timelineData - Array of minute-level entries from /api/timeline
     */
    function render(timelineData) {
        const container = document.getElementById('timeline-chart');
        if (!container) return;

        // Clear previous
        container.innerHTML = '';

        const width = container.clientWidth;
        const height = container.clientHeight || 56;

        const svg = d3.select(container)
            .append('svg')
            .attr('width', width)
            .attr('height', height)
            .style('display', 'block');

        if (!timelineData || timelineData.length === 0) {
            // Empty state
            svg.append('text')
                .attr('x', width / 2)
                .attr('y', height / 2 + 4)
                .attr('text-anchor', 'middle')
                .attr('fill', 'rgba(240, 240, 245, 0.2)')
                .attr('font-size', '13px')
                .attr('font-family', 'Inter, sans-serif')
                .text('No activity recorded yet — tracking in progress...');
            return;
        }

        // Scale: 1440 minutes → full width
        const xScale = d3.scaleLinear()
            .domain([0, 1440])
            .range([0, width]);

        const minuteWidth = Math.max(width / 1440, 0.6);

        // Render segments
        const segments = svg.selectAll('.timeline-segment')
            .data(timelineData)
            .enter()
            .append('rect')
            .attr('class', 'timeline-segment')
            .attr('x', d => xScale(d.minute))
            .attr('y', 0)
            .attr('width', minuteWidth + 0.5)  // Slight overlap to avoid gaps
            .attr('height', height)
            .attr('fill', d => d.color)
            .attr('opacity', 0.85)
            .style('cursor', 'pointer');

        // Hover interactions
        segments
            .on('mouseenter', function (event, d) {
                d3.select(this)
                    .transition()
                    .duration(100)
                    .attr('opacity', 1)
                    .attr('y', -2)
                    .attr('height', height + 4);

                showTooltip(event, d);
            })
            .on('mousemove', function (event) {
                moveTooltip(event);
            })
            .on('mouseleave', function () {
                d3.select(this)
                    .transition()
                    .duration(200)
                    .attr('opacity', 0.85)
                    .attr('y', 0)
                    .attr('height', height);

                hideTooltip();
            });

        // Current time indicator
        const now = new Date();
        const currentMinute = now.getHours() * 60 + now.getMinutes();
        const nowX = xScale(currentMinute);

        // Only show if we're looking at today
        const dateEl = document.getElementById('current-date');
        const isToday = dateEl && dateEl.textContent.includes('Today');

        if (isToday) {
            const nowGroup = svg.append('g')
                .attr('class', 'timeline-now-group');

            // Vertical line
            nowGroup.append('line')
                .attr('x1', nowX)
                .attr('y1', 0)
                .attr('x2', nowX)
                .attr('y2', height)
                .attr('stroke', '#f43f5e')
                .attr('stroke-width', 2)
                .style('filter', 'drop-shadow(0 0 6px rgba(244, 63, 94, 0.5))');

            // Top dot
            nowGroup.append('circle')
                .attr('cx', nowX)
                .attr('cy', 0)
                .attr('r', 4)
                .attr('fill', '#f43f5e')
                .style('filter', 'drop-shadow(0 0 8px rgba(244, 63, 94, 0.6))');

            // Pulse effect
            const pulse = nowGroup.append('circle')
                .attr('cx', nowX)
                .attr('cy', 0)
                .attr('r', 4)
                .attr('fill', 'none')
                .attr('stroke', '#f43f5e')
                .attr('stroke-width', 1);

            function animatePulse() {
                pulse
                    .attr('r', 4)
                    .attr('opacity', 0.8)
                    .transition()
                    .duration(1500)
                    .attr('r', 12)
                    .attr('opacity', 0)
                    .on('end', animatePulse);
            }
            animatePulse();
        }

        // Trigger animation
        ChronicleAnimations.animateTimeline();
    }

    function showTooltip(event, data) {
        if (!tooltipEl) return;

        const hour = Math.floor(data.minute / 60);
        const min = data.minute % 60;
        const timeStr = `${hour.toString().padStart(2, '0')}:${min.toString().padStart(2, '0')}`;

        tooltipEl.innerHTML = `
            <div class="tt-time">${timeStr}</div>
            <div class="tt-category">
                <span class="tt-dot" style="background:${data.color}"></span>
                ${data.category}
            </div>
            ${data.app ? `<div class="tt-app">${data.app}</div>` : ''}
        `;
        tooltipEl.classList.remove('hidden');
        moveTooltip(event);
    }

    function moveTooltip(event) {
        if (!tooltipEl) return;
        const x = event.clientX + 12;
        const y = event.clientY - 10;
        tooltipEl.style.left = `${x}px`;
        tooltipEl.style.top = `${y}px`;
    }

    function hideTooltip() {
        if (tooltipEl) {
            tooltipEl.classList.add('hidden');
        }
    }

    /**
     * Handle window resize.
     */
    function handleResize(timelineData) {
        if (timelineData) {
            render(timelineData);
        }
    }

    return {
        init,
        render,
        handleResize,
    };
})();
