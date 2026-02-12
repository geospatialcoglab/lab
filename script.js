// Mobile Navigation Toggle
document.addEventListener('DOMContentLoaded', function() {
    const navToggle = document.querySelector('.nav-toggle');
    const navMenu = document.querySelector('.nav-menu');
    
    if (navToggle) {
        navToggle.addEventListener('click', function() {
            navMenu.classList.toggle('nav-open');
            navToggle.classList.toggle('nav-open');
        });
    }
    
    // Close mobile menu when clicking a link
    const navLinks = document.querySelectorAll('.nav-menu a');
    navLinks.forEach(link => {
        link.addEventListener('click', function() {
            navMenu.classList.remove('nav-open');
            navToggle.classList.remove('nav-open');
        });
    });
    
    // Handle dropdowns on mobile
    const dropdowns = document.querySelectorAll('.nav-dropdown > a');
    dropdowns.forEach(dropdown => {
        dropdown.addEventListener('click', function(e) {
            if (window.innerWidth <= 900) {
                const dropdownMenu = this.parentElement.querySelector('.dropdown-menu');
                // Only prevent default if there's actually a dropdown menu
                if (dropdownMenu) {
                    e.preventDefault();
                    this.parentElement.classList.toggle('dropdown-open');
                }
            }
        });
    });
});
