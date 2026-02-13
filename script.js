// Mobile Navigation Toggle
document.addEventListener('DOMContentLoaded', function() {
    const navToggle = document.querySelector('.nav-toggle');
    const navMenu = document.querySelector('.nav-menu');
    
    if (!navToggle || !navMenu) return;
    
    navToggle.addEventListener('click', function() {
        navMenu.classList.toggle('nav-open');
        navToggle.classList.toggle('nav-open');
    });
    
    // Close mobile menu when clicking a link (but not dropdown parents)
    const navLinks = document.querySelectorAll('.nav-menu a');
    navLinks.forEach(function(link) {
        link.addEventListener('click', function() {
            // Don't close menu if this is a dropdown parent on mobile
            var parent = this.parentElement;
            if (parent && parent.classList.contains('nav-dropdown')) {
                var hasDropdown = parent.querySelector('.dropdown-menu');
                if (window.innerWidth <= 900 && hasDropdown) {
                    return; // Let the dropdown handler deal with it
                }
            }
            navMenu.classList.remove('nav-open');
            navToggle.classList.remove('nav-open');
        });
    });
    
    // Handle dropdowns on mobile
    var dropdowns = document.querySelectorAll('.nav-dropdown > a');
    dropdowns.forEach(function(dropdown) {
        dropdown.addEventListener('click', function(e) {
            if (window.innerWidth <= 900) {
                var parent = this.parentElement;
                if (parent) {
                    var dropdownMenu = parent.querySelector('.dropdown-menu');
                    // Only prevent default if there's actually a dropdown menu
                    if (dropdownMenu) {
                        e.preventDefault();
                        parent.classList.toggle('dropdown-open');
                    }
                }
            }
        });
    });
});
