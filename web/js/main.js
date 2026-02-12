// Autonomous Research Press - Main JavaScript

// ====================================
// Dark Mode
// ====================================

// Initialize theme
function initTheme() {
    const savedTheme = localStorage.getItem('theme');
    const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    
    if (savedTheme) {
        document.documentElement.setAttribute('data-theme', savedTheme);
    } else if (systemPrefersDark) {
        document.documentElement.setAttribute('data-theme', 'dark');
    }
}

// Toggle theme
function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    
    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
}

// Initialize theme before DOM loads to prevent flash
initTheme();

document.addEventListener('DOMContentLoaded', () => {
    // ====================================
    // Theme Toggle Button
    // ====================================
    const themeToggle = document.querySelector('.theme-toggle');
    if (themeToggle) {
        themeToggle.addEventListener('click', toggleTheme);
    }

    // Listen for system theme changes
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
        if (!localStorage.getItem('theme')) {
            document.documentElement.setAttribute('data-theme', e.matches ? 'dark' : 'light');
        }
    });

    // ====================================
    // Smart Header: Hide on scroll down, show on scroll up
    // ====================================
    const header = document.querySelector('.site-header');
    let lastScrollTop = 0;
    let scrollThreshold = 10; // Minimum scroll to trigger hide/show
    
    if (header) {
        window.addEventListener('scroll', () => {
            const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
            
            // Don't hide header at very top of page
            if (scrollTop < 100) {
                header.classList.remove('header-hidden');
                lastScrollTop = scrollTop;
                return;
            }
            
            // Check scroll direction
            if (Math.abs(scrollTop - lastScrollTop) < scrollThreshold) {
                return;
            }
            
            if (scrollTop > lastScrollTop) {
                // Scrolling down
                header.classList.add('header-hidden');
            } else {
                // Scrolling up
                header.classList.remove('header-hidden');
            }
            
            lastScrollTop = scrollTop;
        }, { passive: true });
    }

    // ====================================
    // Homepage: Article Card Hover Effects
    // ====================================
    const cards = document.querySelectorAll('.article-card:not(.placeholder-card)');
    cards.forEach(card => {
        card.addEventListener('mouseenter', () => {
            card.style.transform = 'translateY(-6px)';
        });
        card.addEventListener('mouseleave', () => {
            card.style.transform = '';
        });
    });

    // ====================================
    // Article Page: TOC Functionality
    // ====================================
    
    // Mobile TOC Toggle
    const tocToggle = document.querySelector('.toc-toggle');
    const tocSidebar = document.querySelector('.toc-sidebar');
    
    if (tocToggle && tocSidebar) {
        tocToggle.addEventListener('click', () => {
            tocSidebar.classList.toggle('active');
        });

        // Close TOC when clicking outside
        tocSidebar.addEventListener('click', (e) => {
            if (e.target === tocSidebar) {
                tocSidebar.classList.remove('active');
            }
        });

        // Close TOC when clicking a link
        const tocLinks = tocSidebar.querySelectorAll('a');
        tocLinks.forEach(link => {
            link.addEventListener('click', () => {
                tocSidebar.classList.remove('active');
            });
        });
    }

    // Smooth scroll for anchor links with proper offset
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                const headerHeight = header ? header.offsetHeight : 80;
                const offset = 20; // Extra padding
                const targetPosition = target.getBoundingClientRect().top + window.pageYOffset - headerHeight - offset;
                
                window.scrollTo({
                    top: targetPosition,
                    behavior: 'smooth'
                });
            }
        });
    });

    // Active section highlighting in TOC
    const sections = document.querySelectorAll('.section[id]');
    const tocNavLinks = document.querySelectorAll('.toc-nav a');

    function highlightActiveSection() {
        let currentSection = '';
        const headerHeight = header ? header.offsetHeight : 80;
        const scrollPosition = window.scrollY + headerHeight + 50;

        sections.forEach(section => {
            const sectionTop = section.offsetTop;
            const sectionBottom = sectionTop + section.offsetHeight;

            if (scrollPosition >= sectionTop && scrollPosition < sectionBottom) {
                currentSection = section.getAttribute('id');
            }
        });

        tocNavLinks.forEach(link => {
            link.classList.remove('active');
            const href = link.getAttribute('href');
            if (href === `#${currentSection}`) {
                link.classList.add('active');
            }
        });
    }

    // Throttle scroll event for performance
    let scrollTimeout;
    if (sections.length > 0) {
        window.addEventListener('scroll', () => {
            if (!scrollTimeout) {
                scrollTimeout = setTimeout(() => {
                    highlightActiveSection();
                    scrollTimeout = null;
                }, 100);
            }
        }, { passive: true });

        // Initial highlight
        highlightActiveSection();
    }

    // ====================================
    // Utility: Copy code blocks on click
    // ====================================
    document.querySelectorAll('.code-block, .breakdown-chart').forEach(block => {
        block.style.cursor = 'pointer';
        block.title = 'Click to copy';

        block.addEventListener('click', async () => {
            const text = block.textContent;
            try {
                await navigator.clipboard.writeText(text);
                
                // Visual feedback
                const originalBg = block.style.backgroundColor;
                const isBreakdown = block.classList.contains('breakdown-chart');
                block.style.backgroundColor = '#10b981';
                block.style.transition = 'background-color 0.3s';

                setTimeout(() => {
                    block.style.backgroundColor = originalBg;
                }, 300);
            } catch (err) {
                console.error('Failed to copy:', err);
            }
        });
    });

    console.log('Autonomous Research Press loaded');
});
