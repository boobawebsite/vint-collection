// ===================================================
// VENT ATELIER: DUAL-MODE SHOWCASE CONTROLLER
// 1. Desktop (>= 768px): 3D Solar System & Planetary Orbit
// 2. Mobile (< 768px): Luxury Peek-Carousel (Matching Exact User Proportions)
// ===================================================

document.addEventListener('DOMContentLoaded', () => {

    // ===================================================
    // 1. MOBILE CAROUSEL CONTROLLER (< 768px)
    // ===================================================
    function initMobileCarousel() {
        const track = document.getElementById('mobileCarouselTrack');
        const slides = document.querySelectorAll('.mobile-slide');
        const titleEl = document.getElementById('mobileActiveTitle');
        const subtitleEl = document.getElementById('mobileActiveSubtitle');
        const exploreBtn = document.getElementById('mobileExploreBtn');
        const dotsContainer = document.getElementById('mobileDots');

        if (!track || slides.length === 0) return;

        let activeIndex = 0;
        let isUserScrolling = false;
        let scrollTimeout = null;

        // Create 6 Pagination Dots
        if (dotsContainer) {
            dotsContainer.innerHTML = '';
            slides.forEach((slide, i) => {
                const dot = document.createElement('button');
                dot.type = 'button';
                dot.className = `mobile-dot h-1.5 rounded-full transition-all duration-300 cursor-pointer ${i === 0 ? 'w-5 bg-black' : 'w-1.5 bg-neutral-300'}`;
                dot.setAttribute('aria-label', `Go to slide ${i + 1}`);
                dot.addEventListener('click', (e) => {
                    e.stopPropagation();
                    scrollToSlide(i);
                });
                dotsContainer.appendChild(dot);
            });
        }

        // Scroll track so slide i is centered in viewport
        function scrollToSlide(index) {
            if (index < 0 || index >= slides.length) return;
            const targetSlide = slides[index];
            const trackWidth = track.clientWidth;
            const slideLeft = targetSlide.offsetLeft;
            const slideWidth = targetSlide.offsetWidth;
            const scrollPos = slideLeft - (trackWidth / 2) + (slideWidth / 2);
            track.scrollTo({ left: scrollPos, behavior: 'smooth' });
            updateActiveState(index);
        }

        // Update active UI (border, scale, opacity, title, dots, explore link)
        function updateActiveState(index) {
            if (index === activeIndex && titleEl && titleEl.textContent === slides[index].getAttribute('data-title')) {
                return;
            }
            activeIndex = index;
            const currentSlide = slides[index];
            if (!currentSlide) return;

            // Update Slide Visuals
            slides.forEach((s, idx) => {
                if (idx === index) {
                    s.classList.remove('opacity-70', 'scale-95', 'border-black/15', 'shadow-md');
                    s.classList.add('opacity-100', 'scale-100', 'border-2', 'border-black', 'shadow-xl');
                    const img = s.querySelector('img');
                    if (img) img.classList.remove('grayscale');
                } else {
                    s.classList.remove('opacity-100', 'scale-100', 'border-2', 'border-black', 'shadow-xl');
                    s.classList.add('opacity-70', 'scale-95', 'border', 'border-black/15', 'shadow-md');
                }
            });

            // Update Text & CTA
            const title = currentSlide.getAttribute('data-title') || 'Vent Collection';
            const subtitle = currentSlide.getAttribute('data-subtitle') || 'Vintage Atelier';
            const href = currentSlide.getAttribute('data-href') || '/vintage';

            if (titleEl) titleEl.textContent = title;
            if (subtitleEl) subtitleEl.textContent = subtitle;
            if (exploreBtn) exploreBtn.href = href;

            // Update Dots
            if (dotsContainer) {
                const dots = dotsContainer.querySelectorAll('.mobile-dot');
                dots.forEach((dot, idx) => {
                    if (idx === index) {
                        dot.className = 'mobile-dot h-1.5 rounded-full transition-all duration-300 cursor-pointer w-5 bg-black';
                    } else {
                        dot.className = 'mobile-dot h-1.5 rounded-full transition-all duration-300 cursor-pointer w-1.5 bg-neutral-300';
                    }
                });
            }
        }

        // Detect centered slide on scroll
        function handleScroll() {
            const trackCenter = track.scrollLeft + (track.clientWidth / 2);
            let closestIndex = 0;
            let closestDist = Infinity;

            slides.forEach((slide, i) => {
                const slideCenter = slide.offsetLeft + (slide.offsetWidth / 2);
                const dist = Math.abs(slideCenter - trackCenter);
                if (dist < closestDist) {
                    closestDist = dist;
                    closestIndex = i;
                }
            });

            updateActiveState(closestIndex);
        }

        track.addEventListener('scroll', () => {
            isUserScrolling = true;
            handleScroll();
            clearTimeout(scrollTimeout);
            scrollTimeout = setTimeout(() => {
                isUserScrolling = false;
            }, 150);
        }, { passive: true });

        // Slide Clicks
        slides.forEach((slide, i) => {
            slide.addEventListener('click', (e) => {
                if (i === activeIndex) {
                    // Navigate to collection
                    const href = slide.getAttribute('data-href') || '/vintage';
                    window.location.href = href;
                } else {
                    // Smoothly center this slide
                    e.preventDefault();
                    scrollToSlide(i);
                }
            });
        });

        // Initialize first slide as active
        updateActiveState(0);
    }

    // ===================================================
    // 2. DESKTOP 3D SOLAR SYSTEM CONTROLLER (>= 768px)
    // STRICTLY UNTOUCHED DESKTOP PLANETARY ORBIT
    // ===================================================
    function initDesktopSolar() {
        const stage = document.getElementById('solarStage');
        const planets = document.querySelectorAll('.planet-item');
        const viewport = document.getElementById('solarViewport');
        if (!stage || planets.length === 0 || !viewport) return;

        let currentAngle = 0;
        let targetAngle = 0;
        let orbitSpeed = 0.25; // Continuous degrees per frame
        let isPaused = false;
        let isDragging = false;
        let startX = 0;
        let lastX = 0;
        let velocity = 0;
        let dragDistance = 0;

        const totalPlanets = planets.length;
        const angleStep = 360 / totalPlanets;

        function getRadius() {
            const w = window.innerWidth;
            if (w < 1024) return 360; // Tablet
            if (w < 1440) return 460; // Laptop
            return 520; // Large desktop
        }

        function updatePlanetsPosition() {
            const radius = getRadius();

            planets.forEach((planet, index) => {
                const baseAngle = (index * angleStep) + currentAngle;
                const rad = (baseAngle * Math.PI) / 180;

                const x = Math.sin(rad) * radius;
                const z = Math.cos(rad) * (radius * 0.45);
                const y = (Math.cos(rad) * (radius * 0.08));

                const normZ = (z + (radius * 0.45)) / (radius * 0.9);
                const scale = 0.75 + (normZ * 0.32);
                const opacity = 0.42 + (normZ * 0.58);
                const zIndex = Math.floor(normZ * 100);

                planet.style.transform = `translate3d(${x}px, ${y}px, ${z}px) translate(-50%, -50%) scale(${scale})`;
                planet.style.opacity = opacity;
                planet.style.zIndex = zIndex;

                if (normZ > 0.88) {
                    planet.classList.add('is-focused');
                } else {
                    planet.classList.remove('is-focused');
                }
            });
        }

        function animate() {
            // Only animate if desktop viewport is visible
            if (window.innerWidth >= 768) {
                if (!isDragging) {
                    if (!isPaused) {
                        targetAngle += orbitSpeed;
                    }
                    currentAngle += (targetAngle - currentAngle) * 0.08;
                    currentAngle += velocity;
                    velocity *= 0.92;
                } else {
                    currentAngle = targetAngle;
                }
                updatePlanetsPosition();
            }
            requestAnimationFrame(animate);
        }

        requestAnimationFrame(animate);

        // Desktop Mouse Drag Controls
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

        viewport.addEventListener('mouseenter', () => { isPaused = true; });
        viewport.addEventListener('mouseleave', () => { isPaused = false; });

        // Hover Color Reveal on Desktop
        planets.forEach((planet) => {
            planet.addEventListener('mouseenter', () => {
                planets.forEach(p => { if (p !== planet) p.classList.remove('show-color'); });
                planet.classList.add('show-color');
            });

            planet.addEventListener('mouseleave', () => {
                planet.classList.remove('show-color');
            });

            planet.addEventListener('click', (e) => {
                if (dragDistance > 6) return;
                e.stopPropagation();
                const href = planet.getAttribute('data-href') || '/vintage';
                window.location.href = href;
            });
        });

        viewport.addEventListener('click', (e) => {
            if (dragDistance > 6) return;
            if (!e.target.closest('.planet-item')) {
                planets.forEach(p => p.classList.remove('show-color'));
            }
        });
    }

    // Initialize based on screen width
    initMobileCarousel();
    initDesktopSolar();

    // Re-evaluate on window resize
    let resizeTimer;
    window.addEventListener('resize', () => {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(() => {
            if (window.innerWidth < 768) {
                initMobileCarousel();
            } else {
                initDesktopSolar();
            }
        }, 200);
    });

});
