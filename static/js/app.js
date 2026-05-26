/**
 * Chronicle — Main Application Controller
 * Orchestrates data fetching, rendering, and auto-refresh.
 */

const ChronicleApp = (() => {
    const API_BASE = '';
    const REFRESH_INTERVAL = 15000; // 15 seconds

    let currentDate = new Date();
    let timelineData = null;
    let refreshTimer = null;
    let isInitialized = false;

    /**
     * Initialize the application.
     */
    async function init() {
        ChronicleTimeline.init();

        // Load initial data
        try {
            await loadData();
        } catch (e) {
            console.warn('Initial data load failed, starting with empty state:', e);
        }

        // Animate app entrance
        ChronicleAnimations.animateAppEntrance(() => {
            ChronicleAnimations.setupScrollAnimations();
            isInitialized = true;
        });

        // Setup event listeners
        setupEventListeners();

        // Start auto-refresh
        startAutoRefresh();

        // Update time display
        updateTimeDisplay();
        setInterval(updateTimeDisplay, 1000);
    }

    function setupEventListeners() {
        document.getElementById('btn-prev-date').addEventListener('click', () => navigateDate(-1));
        document.getElementById('btn-next-date').addEventListener('click', () => navigateDate(1));

        // Handle window resize
        let resizeTimer;
        window.addEventListener('resize', () => {
            clearTimeout(resizeTimer);
            resizeTimer = setTimeout(() => {
                if (timelineData) {
                    ChronicleTimeline.render(timelineData);
                }
                // Re-render charts
                loadData(true);
            }, 250);
        });
    }

    /**
     * Navigate to a different date.
     */
    function navigateDate(delta) {
        currentDate = new Date(currentDate.getTime() + delta * 86400000);

        // Don't go into the future
        const today = new Date();
        today.setHours(23, 59, 59, 999);
        if (currentDate > today) {
            currentDate = new Date();
        }

        updateDateDisplay();
        loadData(true);
    }

    /**
     * Update the date display in the header.
     */
    function updateDateDisplay() {
        const el = document.getElementById('current-date');
        const today = new Date();

        if (isSameDay(currentDate, today)) {
            el.textContent = 'Today';
        } else if (isSameDay(currentDate, new Date(today.getTime() - 86400000))) {
            el.textContent = 'Yesterday';
        } else {
            el.textContent = currentDate.toLocaleDateString('en-US', {
                weekday: 'short',
                month: 'short',
                day: 'numeric',
            });
        }

        // Show/hide live indicator
        const liveEl = document.getElementById('live-indicator');
        if (liveEl) {
            liveEl.style.display = isSameDay(currentDate, today) ? 'flex' : 'none';
        }
    }

    /**
     * Load all data for the current date.
     */
    async function loadData(skipAnimation = false) {
        const dateStr = formatDate(currentDate);

        try {
            // Fetch all data in parallel
            const [todayData, timelineResp, sessionsResp] = await Promise.all([
                fetchJSON(`/api/metrics/${dateStr}`),
                fetchJSON(`/api/timeline/${dateStr}`),
                fetchJSON(`/api/sessions/${dateStr}`),
            ]);

            // Update date display
            updateDateDisplay();

            // Render focus score
            renderFocusScore(todayData.focus_score, todayData.stats);

            // Render stats
            renderStats(todayData.stats);

            // Render timeline
            timelineData = timelineResp.timeline;
            ChronicleTimeline.render(timelineData);
            document.getElementById('timeline-event-count').textContent =
                `${timelineResp.total_events} events`;

            // Render entropy chart
            ChronicleCharts.renderEntropyChart(todayData.hourly_entropy);

            // Render categories
            const categories = await fetchJSON('/api/categories');
            if (todayData.stats && todayData.stats.top_categories) {
                ChronicleCharts.renderCategoryDonut(todayData.stats.top_categories, categories);
                ChronicleCharts.renderCategoryBars(todayData.stats.top_categories, categories);
            }

            // Render sessions
            renderSessions(sessionsResp.sessions);
            document.getElementById('session-count').textContent =
                `${sessionsResp.total_sessions} sessions`;

            // Pulse refresh indicator
            if (isInitialized) {
                ChronicleAnimations.pulseRefresh();
            }

        } catch (error) {
            console.error('Failed to load data:', error);
        }
    }

    /**
     * Render the focus score in the hero ring.
     */
    function renderFocusScore(score, stats) {
        ChronicleAnimations.animateFocusRing(score);

        // Update descriptor
        const descriptor = document.getElementById('focus-descriptor');
        if (descriptor) {
            if (!stats || stats.total_tracked_seconds === 0) {
                descriptor.textContent = 'Waiting for data...';
            } else if (score >= 0.8) {
                descriptor.textContent = '🎯 Deep Focus Mode';
            } else if (score >= 0.6) {
                descriptor.textContent = '✨ Solid Focus';
            } else if (score >= 0.4) {
                descriptor.textContent = '📊 Moderate Focus';
            } else if (score >= 0.2) {
                descriptor.textContent = '🔀 Scattered Attention';
            } else {
                descriptor.textContent = '🌪 Highly Fragmented';
            }
        }
    }

    /**
     * Render the stat cards.
     */
    function renderStats(stats) {
        if (!stats) return;

        const trackedTime = formatDurationLong(stats.total_tracked_seconds || 0);
        const productivePct = `${stats.productive_pct || 0}%`;
        const longestFocus = stats.longest_focus_minutes
            ? `${Math.round(stats.longest_focus_minutes)}m`
            : '0m';
        const switches = stats.context_switches || 0;

        ChronicleAnimations.animateStatValue('stat-tracked-value', trackedTime);
        ChronicleAnimations.animateStatValue('stat-productive-value', productivePct);
        ChronicleAnimations.animateStatValue('stat-focus-streak-value', longestFocus);
        ChronicleAnimations.animateStatValue('stat-switches-value', switches);
    }

    /**
     * Render session cards.
     */
    function renderSessions(sessions) {
        const container = document.getElementById('sessions-list');
        if (!container) return;
        container.innerHTML = '';

        if (!sessions || sessions.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">◇</div>
                    <div class="empty-state-title">No sessions yet</div>
                    <div class="empty-state-text">
                        Sessions will appear here as you work. Chronicle is tracking
                        your activity and will stitch it into coherent focus sessions.
                    </div>
                </div>`;
            return;
        }

        // Show sessions in reverse chronological order (most recent first)
        const sorted = [...sessions].reverse();

        sorted.forEach(session => {
            const card = document.createElement('div');
            card.className = 'session-card';

            const startTime = formatTimeStr(session.start_time);
            const endTime = formatTimeStr(session.end_time);

            card.innerHTML = `
                <div class="session-accent" style="background: ${session.color || '#6b7280'}"></div>
                <div class="session-icon" style="background: ${hexToRgba(session.color || '#6b7280', 0.12)}">
                    ${session.icon || '◇'}
                </div>
                <div class="session-info">
                    <span class="session-category">${session.category}</span>
                    <span class="session-app">${session.app_name || 'Unknown'}</span>
                    <span class="session-time">${startTime} → ${endTime}</span>
                </div>
                <div class="session-duration">
                    <div class="session-duration-value">${session.duration_formatted || formatDurationShort(session.duration_seconds)}</div>
                    <div class="session-duration-label">duration</div>
                </div>
            `;
            container.appendChild(card);
        });

        // Animate cards
        if (isInitialized) {
            ChronicleAnimations.animateSessionCards();
        }
    }

    /**
     * Start auto-refresh timer.
     */
    function startAutoRefresh() {
        if (refreshTimer) clearInterval(refreshTimer);
        refreshTimer = setInterval(() => {
            const today = new Date();
            if (isSameDay(currentDate, today)) {
                loadData(true);
            }
        }, REFRESH_INTERVAL);
    }

    /**
     * Update the server time display.
     */
    function updateTimeDisplay() {
        const el = document.getElementById('server-time');
        if (el) {
            const now = new Date();
            el.textContent = now.toLocaleTimeString('en-US', {
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
                hour12: false,
            });
        }
    }

    // ── Utility Functions ──────────────────────────────────────────────

    async function fetchJSON(url) {
        const response = await fetch(API_BASE + url);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
    }

    function formatDate(date) {
        const y = date.getFullYear();
        const m = String(date.getMonth() + 1).padStart(2, '0');
        const d = String(date.getDate()).padStart(2, '0');
        return `${y}-${m}-${d}`;
    }

    function isSameDay(d1, d2) {
        return d1.getFullYear() === d2.getFullYear()
            && d1.getMonth() === d2.getMonth()
            && d1.getDate() === d2.getDate();
    }

    function formatDurationLong(seconds) {
        if (seconds < 60) return `${Math.round(seconds)}s`;
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        if (h > 0) return `${h}h ${m}m`;
        return `${m}m`;
    }

    function formatDurationShort(seconds) {
        if (!seconds) return '0s';
        if (seconds < 60) return `${Math.round(seconds)}s`;
        if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        return `${h}h ${m}m`;
    }

    function formatTimeStr(timestamp) {
        if (!timestamp) return '';
        // Extract time from "YYYY-MM-DD HH:MM:SS"
        const parts = timestamp.split(' ');
        if (parts.length >= 2) {
            return parts[1].substring(0, 5); // HH:MM
        }
        return timestamp;
    }

    function hexToRgba(hex, alpha) {
        const r = parseInt(hex.slice(1, 3), 16);
        const g = parseInt(hex.slice(3, 5), 16);
        const b = parseInt(hex.slice(5, 7), 16);
        return `rgba(${r}, ${g}, ${b}, ${alpha})`;
    }

    return {
        init,
    };
})();

// ── Boot ───────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    // Small delay to let fonts load
    setTimeout(() => {
        ChronicleApp.init();
    }, 300);
});
