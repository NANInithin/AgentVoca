# Landing-page deployment

Production URL: **https://agentvoca.naninithin.me** (GitHub Pages, deployed by `.github/workflows/website.yml`).

- `website/` holds the static page (`index.html`) and a `build` script that writes `website/dist/`.
- `scripts/build_website.mjs` runs `npm ci` + `npm run build -- --base=/` and validates the output into `build/website`.
- Pushes to `main` that touch the website redeploy; PRs and `website/landing-page` only build a `website-preview` artifact.

## One-time GitHub settings
1. **Settings → Pages → Source:** GitHub Actions.
2. **Settings → Pages → Custom domain:** `agentvoca.naninithin.me`, then **Enforce HTTPS**.
3. **Settings → Environments → github-pages:** deployment branches = `main` only.
4. DNS: `CNAME agentvoca → naninithin.github.io`.

## Local check
```
node --test tests/website_pipeline.test.mjs
node scripts/build_website.mjs
python -m http.server 4173 --directory build/website
```
