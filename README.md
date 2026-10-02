# adembtr.github.io

Personal website of **Adem Batur** — Computer Engineering student at Sakarya University.
Live at <https://adembtr.github.io/>.

- Hero: a 3D point cloud of my own portrait (person segmentation + Depth Anything V2 → 100k coloured points),
  rendered with Three.js and a custom shader. It turns with the pointer, disperses on scroll and re-forms.
- Sections: highlights, about, projects (with real media and detail views), experience, education, honors, skills, contact and a CV PDF.
- English by default, Turkish toggle. Static site, Vite build, no tracking.

## Development

```bash
npm install
npm run dev        # http://localhost:5173
npm run build      # -> docs/ (served by GitHub Pages and Netlify)
```

Regenerating assets (optional, needs the source files on my machine):

```bash
python3 tools/make_pointcloud.py <photo.jpg> public/assets/cloud   # GPU, downloads RMBG-1.4 + Depth Anything V2 Small
bash tools/media.sh && python3 tools/convert_images.py              # video clips + WebP images
node tools/make_pdf.mjs                                             # CV PDF from tools/cv.html
node tools/qa.mjs                                                   # screenshots, console errors, links, overflow
```

## Licence

Code: MIT. Texts, photos, videos and the point cloud are © Adem Batur, all rights reserved.
