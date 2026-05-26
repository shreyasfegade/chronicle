/**
 * Chronicle — GSAP Animation Orchestration
 * Handles all entrance animations, transitions, and micro-interactions.
 */

const ChronicleAnimations = (() => {
    // Register GSAP plugins
    gsap.registerPlugin(ScrollTrigger);

    /**
     * Animate the loading screen exit and app entrance.
     */
    function animateAppEntrance(onComplete) {
        const tl = gsap.timeline({
            onComplete: onComplete,
        });

        // Fade out loading screen
        tl.to('#loading-screen', {
            opacity: 0,
            duration: 0.5,
            ease: 'power2.inOut',
        });

        // Show app
        tl.call(() => {
            document.getElementById('loading-screen').classList.add('hidden');
            document.getElementById('app').classList.remove('hidden');
        });

        // Animate header
        tl.from('#app-header', {
            y: -30,
            opacity: 0,
            duration: 0.6,
            ease: 'power3.out',
        });

        // Animate hero section
        tl.from('#focus-score-card', {
            scale: 0.9,
            opacity: 0,
            duration: 0.7,
            ease: 'back.out(1.4)',
        }, '-=0.3');

        // Animate stat cards with stagger
        tl.from('.stat-card', {
            y: 30,
            opacity: 0,
            duration: 0.5,
            stagger: 0.1,
            ease: 'power3.out',
        }, '-=0.4');

        return tl;
    }

    /**
     * Animate the focus score ring fill.
     */
    function animateFocusRing(score) {
        const ring = document.getElementById('focus-ring');
        if (!ring) return;

        const circumference = 2 * Math.PI * 85; // r=85
        const offset = circumference * (1 - score);

        // Update gradient colors based on score
        const stop1 = document.getElementById('grad-stop-1');
        const stop2 = document.getElementById('grad-stop-2');

        if (score >= 0.7) {
            // Emerald to teal — great focus
            stop1.setAttribute('stop-color', '#10b981');
            stop2.setAttribute('stop-color', '#14b8a6');
        } else if (score >= 0.4) {
            // Indigo to violet — moderate
            stop1.setAttribute('stop-color', '#6366f1');
            stop2.setAttribute('stop-color', '#8b5cf6');
        } else {
            // Amber to rose — fragmented
            stop1.setAttribute('stop-color', '#f59e0b');
            stop2.setAttribute('stop-color', '#f43f5e');
        }

        gsap.to(ring, {
            strokeDashoffset: offset,
            duration: 1.8,
            ease: 'power3.out',
            delay: 0.3,
        });

        // Subtle continuous rotation on the ring for a living feel
        gsap.to(ring, {
            rotation: 360,
            transformOrigin: '100px 100px',
            duration: 60,
            ease: 'none',
            repeat: -1,
            delay: 2,
        });

        // Animate the score number
        const scoreText = document.getElementById('focus-score-text');
        if (scoreText) {
            gsap.to({ val: 0 }, {
                val: Math.round(score * 100),
                duration: 1.5,
                ease: 'power2.out',
                delay: 0.5,
                onUpdate: function () {
                    scoreText.textContent = Math.round(this.targets()[0].val);
                }
            });
        }

        // Subtle floating animation on the focus ring container
        const container = document.querySelector('.focus-ring-container');
        if (container) {
            gsap.to(container, {
                y: -3,
                duration: 3,
                ease: 'sine.inOut',
                yoyo: true,
                repeat: -1,
            });
        }
    }

    /**
     * Animate stat value counters.
     */
    function animateStatValue(elementId, targetValue, suffix = '') {
        const el = document.getElementById(elementId);
        if (!el) return;

        if (typeof targetValue === 'string') {
            // For string values, just set and fade in
            gsap.fromTo(el, { opacity: 0, y: 10 }, {
                opacity: 1, y: 0, duration: 0.5, ease: 'power2.out',
                onStart: () => { el.textContent = targetValue; }
            });
        } else {
            // For numeric values, animate count
            gsap.to({ val: 0 }, {
                val: targetValue,
                duration: 1.2,
                ease: 'power2.out',
                onUpdate: function () {
                    el.textContent = Math.round(this.targets()[0].val) + suffix;
                }
            });
        }
    }

    /**
     * Animate sections as they scroll into view.
     */
    function setupScrollAnimations() {
        const sections = document.querySelectorAll('.section');
        sections.forEach(section => {
            gsap.from(section, {
                y: 40,
                opacity: 0,
                duration: 0.7,
                ease: 'power3.out',
                scrollTrigger: {
                    trigger: section,
                    start: 'top 85%',
                    toggleActions: 'play none none none',
                },
            });
        });
    }

    /**
     * Animate session cards with staggered entrance.
     */
    function animateSessionCards() {
        const cards = document.querySelectorAll('.session-card');
        gsap.from(cards, {
            x: -30,
            opacity: 0,
            duration: 0.5,
            stagger: 0.06,
            ease: 'power3.out',
        });
    }

    /**
     * Animate category bar fills.
     */
    function animateCategoryBars() {
        const fills = document.querySelectorAll('.category-bar-fill');
        fills.forEach(fill => {
            const targetWidth = fill.getAttribute('data-width') || '0%';
            fill.style.width = '0%';
            gsap.to(fill, {
                width: targetWidth,
                duration: 1,
                ease: 'power3.out',
                delay: 0.2,
            });
        });
    }

    /**
     * Animate timeline segments appearing.
     */
    function animateTimeline() {
        const segments = document.querySelectorAll('.timeline-segment');
        if (segments.length === 0) return;

        gsap.from(segments, {
            scaleY: 0,
            opacity: 0,
            duration: 0.4,
            stagger: {
                each: 0.003,
                from: 'start',
            },
            ease: 'power2.out',
            transformOrigin: 'bottom center',
        });
    }

    /**
     * Animate entropy bars growing.
     */
    function animateEntropyBars() {
        const bars = document.querySelectorAll('.entropy-bar');
        gsap.from(bars, {
            scaleY: 0,
            duration: 0.6,
            stagger: 0.03,
            ease: 'back.out(1.2)',
            transformOrigin: 'bottom center',
        });
    }

    /**
     * Pulse animation for live indicator on data refresh.
     */
    function pulseRefresh() {
        gsap.fromTo('.live-dot', {
            scale: 1,
            boxShadow: '0 0 8px rgba(16, 185, 129, 0.5)',
        }, {
            scale: 1.5,
            boxShadow: '0 0 20px rgba(16, 185, 129, 0.8)',
            duration: 0.3,
            yoyo: true,
            repeat: 1,
            ease: 'power2.inOut',
        });
    }

    /**
     * Smooth data update transition.
     */
    function transitionDataUpdate(containerSelector, callback) {
        const container = document.querySelector(containerSelector);
        if (!container) {
            callback();
            return;
        }

        gsap.to(container, {
            opacity: 0.3,
            duration: 0.15,
            ease: 'power2.in',
            onComplete: () => {
                callback();
                gsap.to(container, {
                    opacity: 1,
                    duration: 0.3,
                    ease: 'power2.out',
                });
            }
        });
    }

    return {
        animateAppEntrance,
        animateFocusRing,
        animateStatValue,
        setupScrollAnimations,
        animateSessionCards,
        animateCategoryBars,
        animateTimeline,
        animateEntropyBars,
        pulseRefresh,
        transitionDataUpdate,
    };
})();
