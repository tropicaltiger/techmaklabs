# Tech Mak Labs — GitHub Pages website

A responsive, static landing page for Tech Mak Labs. It uses the previously selected Logo Variation 08 (Future Focus) and the tagline “BUILD • EXPERIMENT • LAUNCH”.

## Files
- `index.html` — complete website, responsive styling, interaction, metadata and Organization schema.
- `assets/techmaklabs-logo.png` — cropped Variation 08 logo from the original logo style sheet.
- `assets/techmaklabs-logo-small.png` — small logo image used as a simple favicon.
- `robots.txt` and `sitemap.xml` — basic crawl files.

## Before launch
1. **Set up the contact email.** The form and footer currently use `hello@techmaklabs.com`. Create that mailbox/alias or replace it with an email address you control in `index.html` before publishing. The idea form uses `mailto:`; it does not send data to a server or store submissions.
2. The website uses Google Fonts via an external stylesheet. If you prefer no external requests, remove the Google Fonts `<link>` and the site will fall back to system sans-serif fonts.
3. The Tech Mak Search panel is clearly labelled as a concept preview, not a live dashboard or a claim of existing product functionality.
4. Check that `https://techmaklabs.com/` is the canonical domain you want to use. If you choose `www`, update the canonical, Open Graph and JSON-LD URLs plus `sitemap.xml`.

## Publish with GitHub Pages
1. Create a GitHub repository (for example, `techmaklabs-website`).
2. Upload `index.html`, `robots.txt`, `sitemap.xml`, and the `assets` folder to the repository root.
3. In the repository, open **Settings → Pages**. Select **Deploy from a branch**, choose `main` and `/ (root)`, then save.
4. Once the GitHub Pages URL works, set the custom domain to `techmaklabs.com` in **Settings → Pages**.
5. Add the exact DNS records GitHub shows to BigRock's DNS manager. Do not guess the values; follow GitHub's current instructions.
6. After DNS verification, enable HTTPS in GitHub Pages. Then check the mobile layout, links, form draft and metadata.

## Local preview
Open `index.html` in a browser. No build step or package installation is required.
