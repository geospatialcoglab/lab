# Geospatial Cognition Lab Website

A clean, professional academic research lab website built for GitHub Pages.

## Features

- Responsive design that works on all devices
- Custom color scheme matching lab branding
- Five main pages: Home, About, People, Publications, and News
- Easy to customize and maintain
- No build process required - pure HTML/CSS

## Color Scheme

- Main Background: #FAF9F6 (Off-White)
- Secondary Background: #E8E8E6 (Soft Pebble)
- Main Text: #43433D (Charcoal)
- Secondary Text: #63633C (Deep Olive)
- Accent: #C25A2E (Burnt Orange)

## Fonts

- Primary (Headings): Fjalla One
- Secondary (Body): Nunito Sans (similar to Futura/Avenir)

## Deployment to GitHub Pages

1. Create a new repository on GitHub (e.g., `geospatial-cognition-lab`)
2. Upload all files from this directory to the repository
3. Go to repository Settings → Pages
4. Under "Source", select "Deploy from a branch"
5. Select the `main` branch and `/ (root)` folder
6. Click Save
7. Your site will be live at: `https://[username].github.io/[repository-name]`

## Customization Guide

### Adding Team Members

Edit `people.html` and add new person cards:

```html
<div class="person-card">
    <div class="person-photo-placeholder">
        <span>Photo</span>
    </div>
    <h3>Name</h3>
    <p class="person-title">Title</p>
    <p class="person-bio">Bio text here.</p>
    <p class="person-contact">email@university.edu</p>
</div>
```

### Adding Publications

Edit `publications.html` and add new publications within the appropriate year section:

```html
<div class="publication">
    <p class="pub-authors">Author names</p>
    <p class="pub-title">Paper title</p>
    <p class="pub-venue"><em>Journal Name</em>, volume(issue), pages.</p>
    <a href="https://doi.org/..." class="pub-link">DOI</a>
</div>
```

### Adding News Items

Edit `news.html` and add new articles:

```html
<article class="news-article">
    <span class="news-date">Month Year</span>
    <h2>News Title</h2>
    <p>News content here.</p>
</article>
```

### Adding Photos

1. Create an `images` folder in your repository
2. Upload photos (recommended: 300x300px for profile photos)
3. Replace the placeholder divs with:

```html
<img src="images/photo-name.jpg" alt="Person Name" class="person-photo">
```

4. Add this CSS to `styles.css`:

```css
.person-photo {
    width: 150px;
    height: 150px;
    border-radius: 50%;
    object-fit: cover;
    margin: 0 auto 1.5rem;
    display: block;
}
```

### Adding a Logo

1. Upload your logo to an `images` folder
2. In each HTML file, replace the nav-brand text with:

```html
<div class="nav-brand">
    <img src="images/logo.png" alt="Geospatial Cognition Lab" style="height: 40px;">
</div>
```

## File Structure

```
├── index.html          # Homepage
├── about.html          # About page
├── people.html         # Team members
├── publications.html   # Research publications
├── news.html          # Lab news and updates
├── styles.css         # All styling
└── README.md          # This file
```

## Browser Support

Works on all modern browsers including Chrome, Firefox, Safari, and Edge.

## License

Feel free to customize this template for your lab's needs.
