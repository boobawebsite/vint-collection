// ===================================================
// 3D SOLAR SYSTEM & PLANETARY CAROUSEL CONTROLLER
// Responsive for Mobile (< 768px) and Desktop (>= 768px)
// ===================================================

document.addEventListener('DOMContentLoaded', () => {
    const stage = document.getElementById('solarStage');
    const planets = document.querySelectorAll('.planet-item');
    if (!stage || planets.length === 0) return;

    let currentAngle = 0;
    let targetAngle = 0;
    let orbitSpeed = 0.25; // Continuous degrees per frame
    let isPaused = false;
    let isDragging = false;
    let startX = 0;
    let lastX = 0;
    let velocity = 0;

    // Number of planets
    const totalPlanets = planets.length;
    const angleStep = 360 / totalPlanets;

    // Mobile Dock Elements
    const mobileDock = document.getElementById('solarMobileDock');
    const activeTitle = document.getElementById('solarActiveTitle');
    const activeSubtitle = document.getElementById('solarActiveSubtitle');
    const activeCta = document.getElementById('solarActiveCta');
    const dotsContainer = document.getElementById('solarDotsContainer');
    let activeMobileIndex = -1;

    // Initialize Mobile Pagination Dots
    if (dotsContainer) {
        dotsContainer.innerHTML = '';
        for (let i = 0; i < totalPlanets; i++) {
            const dot = document.createElement('button');
            dot.type = 'button';
            dot.className = `solar-dot ${i === 0 ? 'active' : ''}`;
            dot.setAttribute('aria-label', `View item ${i + 1}`);
            dot.addEventListener('click', (e) => {
                e.stopPropagation();
                rotateToIndex(i);
            });
            dotsContainer.appendChild(dot);
        }
    }

    // Smoothly rotate to a specific item index
    function rotateToIndex(index) {
        // Desired angle where (index * angleStep) + angle = 0 (mod 360)
        const target = -(index * angleStep);
        const diff = (target - targetAngle) % 360;
        let shortestDiff = diff;
        if (diff > 180) shortestDiff -= 360;
        if (diff < -180) shortestDiff += 360;
        targetAngle += shortestDiff;
        velocity = 0;
    }

    // Update Mobile Dock details
    function updateMobileDock(planet, index) {
        if (!mobileDock) return;
        const title = planet.getAttribute('data-title') || 'Vent Collection';
        const subtitle = planet.getAttribute('data-subtitle') || 'Vintage Atelier';
        const href = planet.getAttribute('data-href') || '/vintage';

        if (activeTitle) activeTitle.textContent = title;
        if (activeSubtitle) activeSubtitle.textContent = subtitle;
        if (activeCta) activeCta.href = href;

        if (dotsContainer) {
            const dots = dotsContainer.querySelectorAll('.solar-dot');
            dots.forEach((dot, i) => {
                if (i === index) {
                    dot.classList.add('active');
                } else {
                    dot.classList.remove('active');
                }
            });
        }
    }

    // Radius of orbit in pixels (Strictly preserving desktop, optimized for mobile)
    function getRadius() {
        const w = window.innerWidth;
        if (w < 380) return 100; // Small mobile (iPhone SE 375px)
        if (w < 480) return 118; // Standard mobile (iPhone 12-16, Galaxy 390-430px)
        if (w < 640) return 150; // Large mobile
        if (w < 768) return 210; // Phablets / small tablets
        // Desktop breakpoints remain 100% UNTOUCHED
        if (w < 1024) return 360; // Tablet
        if (w < 1440) return 460; // Laptop
        return 520; // Large desktop
    }

    function updatePlanetsPosition() {
        const radius = getRadius();
        const isMobile = window.innerWidth < 768;

        let topPlanet = null;
        let topNormZ = -1;
        let topIndex = 0;

        planets.forEach((planet, index) => {
            // Angle in radians
            const baseAngle = (index * angleStep) + currentAngle;
            const rad = (baseAngle * Math.PI) / 180;

            // Coordinates on 3D ellipse
            const x = Math.sin(rad) * radius;
            const z = Math.cos(rad) * (radius * (isMobile ? 0.55 : 0.45)); // Slightly tighter foreshortening on mobile
            const y = (Math.cos(rad) * (radius * 0.08));

            // Normalized Z from 0 (deep back) to 1 (front center)
            const zSpan = radius * (isMobile ? 0.55 : 0.45) * 2;
            const normZ = (z + (zSpan / 2)) / zSpan;

            // Scale & Depth calculations
            let scale, opacity;
            if (isMobile) {
                // Front card: scale 1.0, adjacent cards: scale ~0.78, back cards: scale ~0.62
                scale = 0.65 + (normZ * 0.35);
                opacity = 0.28 + (normZ * 0.72);
            } else {
                // Desktop scale and opacity remain 100% untouched
                scale = 0.75 + (normZ * 0.32);
                opacity = 0.42 + (normZ * 0.58);
            }

            const zIndex = Math.floor(normZ * 100);

            // Apply 3D coordinates
            planet.style.transform = `translate3d(${x}px, ${y}px, ${z}px) translate(-50%, -50%) scale(${scale})`;
            planet.style.opacity = opacity;
            planet.style.zIndex = zIndex;

            // Track closest planet facing user
            if (normZ > topNormZ) {
                topNormZ = normZ;
                topPlanet = planet;
                topIndex = index;
            }

            // Focused class on front item
            if (normZ > 0.86) {
                planet.classList.add('is-focused');
            } else {
                planet.classList.remove('is-focused');
            }
        });

        // Sync Mobile Dock on mobile
        if (isMobile && topPlanet && topIndex !== activeMobileIndex) {
            activeMobileIndex = topIndex;
            updateMobileDock(topPlanet, topIndex);
        }
    }

    // Animation Loop
    function animate() {
        if (!isDragging) {
            if (!isPaused) {
                targetAngle += orbitSpeed;
            }
            // Smooth inertia
            currentAngle += (targetAngle - currentAngle) * 0.08;
            currentAngle += velocity;
            velocity *= 0.92; // friction
        } else {
            currentAngle = targetAngle;
        }

        updatePlanetsPosition();
        requestAnimationFrame(animate);
    }

    requestAnimationFrame(animate);

    // Mouse & Touch Drag Controls
    let dragDistance = 0;
    const viewport = document.getElementById('solarViewport');
    if (viewport) {
        // Desktop Mouse Drag
        viewport.addEventListener('mousedown', (e) => {
            isDragging = true;
            startX = e.clientX;
            lastX = e.clientX;
            dragDistance = 0;
            velocity = 0;
            viewport.style.cursor = 'grabbing';
        });

        window.addEventListener('mousemove', (e) => {
            if (!isDragging) return;
            const delta = e.clientX - lastX;
            dragDistance += Math.abs(delta);
            lastX = e.clientX;
            targetAngle += delta * 0.35;
            velocity = delta * 0.15;
        });

        window.addEventListener('mouseup', () => {
            if (!isDragging) return;
            isDragging = false;
            viewport.style.cursor = 'grab';
        });

        // Mobile Touch Events (Natural Horizontal Swiping)
        let touchStartX = 0;
        let touchStartY = 0;

        viewport.addEventListener('touchstart', (e) => {
            if (e.touches.length === 1) {
                isDragging = true;
                startX = e.touches[0].clientX;
                lastX = e.touches[0].clientX;
                touchStartX = e.touches[0].clientX;
                touchStartY = e.touches[0].clientY;
                dragDistance = 0;
                velocity = 0;
            }
        }, { passive: true });

        window.addEventListener('touchmove', (e) => {
            if (!isDragging || e.touches.length !== 1) return;
            const delta = e.touches[0].clientX - lastX;
            const totalDist = Math.hypot(e.touches[0].clientX - touchStartX, e.touches[0].clientY - touchStartY);
            dragDistance += totalDist;
            lastX = e.touches[0].clientX;
            targetAngle += delta * 0.45;
            velocity = delta * 0.2;
        }, { passive: true });

        window.addEventListener('touchend', () => {
            if (isDragging) {
                isDragging = false;
                // On mobile, gently snap to the nearest item index for clean framing
                if (window.innerWidth < 768) {
                    targetAngle = Math.round(targetAngle / angleStep) * angleStep;
                }
            }
        });

        // Pause on Hover (Desktop)
        viewport.addEventListener('mouseenter', () => { isPaused = true; });
        viewport.addEventListener('mouseleave', () => { isPaused = false; });
    }

    // ===================================================
    // MOUSE HOVER & TOUCH TO REVEAL ORIGINAL IMAGE COLOR
    // ===================================================
    planets.forEach((planet) => {
        // Immediately reveal real color when mouse touches image
        planet.addEventListener('mouseenter', () => {
            planets.forEach(p => { if (p !== planet) p.classList.remove('show-color'); });
            planet.classList.add('show-color');
        });

        planet.addEventListener('mouseleave', () => {
            planet.classList.remove('show-color');
        });

        // Click / tap takes user directly to Apple-inspired Vintage Collection page
        planet.addEventListener('click', (e) => {
            // If user was dragging or swiping, do not trigger navigation
            if (dragDistance > 8) return;

            e.stopPropagation();
            const href = planet.getAttribute('data-href') || '/vintage';
            window.location.href = href;
        });
    });

    // Clicking empty space in the viewport resets all planets back to monochrome
    if (viewport) {
        viewport.addEventListener('click', (e) => {
            if (dragDistance > 8) return;
            if (!e.target.closest('.planet-item')) {
                planets.forEach(p => p.classList.remove('show-color'));
            }
        });
    }

    // Prev / Next Controls (if present)
    const prevBtn = document.getElementById('orbitPrevBtn');
    const nextBtn = document.getElementById('orbitNextBtn');
    const playPauseBtn = document.getElementById('orbitPlayPauseBtn');

    if (prevBtn) {
        prevBtn.addEventListener('click', () => {
            targetAngle -= angleStep;
        });
    }

    if (nextBtn) {
        nextBtn.addEventListener('click', () => {
            targetAngle += angleStep;
        });
    }

    if (playPauseBtn) {
        playPauseBtn.addEventListener('click', () => {
            isPaused = !isPaused;
            const icon = playPauseBtn.querySelector('i');
            if (icon) {
                icon.className = isPaused ? 'fa-solid fa-play' : 'fa-solid fa-pause';
            }
        });
    }

    // Window Resize Handler
    window.addEventListener('resize', () => {
        updatePlanetsPosition();
    });
});
