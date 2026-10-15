# Entry ring and Fluxora home

The frontend uses React 19, Vite and TypeScript. Reusable wheel code lives in
`src/components/ui/works-wheel.tsx`; the `@` alias resolves to `src`.

`EntryPage.tsx` renders the ring immediately on `/`. Its eight cards map to the
Nature, Ocean, Space, Sunset, Aurora, Minimal, Cyberpunk and Rose palettes in
`appearance.tsx`. Card activation, ring title buttons, swatches and the shared
appearance picker apply the selected palette. Local storage retains the selection,
and a storage event synchronizes it across tabs. Palette tokens use complete CSS
colours; Tailwind wheel colours read those values directly.

All eight theme photos and SVG fallbacks are bundled in `public/themes/`.
`public/wheel/` retains generic covers for the reusable wheel's default fallback.
The ring supports pointer drag, scroll, ArrowUp/ArrowDown, Home/End and
Enter/Space activation. A drag suppresses accidental card activation.

After authentication `/app` renders the supplied Fluxora video hero, functional
feature navigation and the existing searchable presentation library. The video
is served locally from `public/hero-loop.mp4`. Reduced motion pauses playback.
Presentation canvas colours remain independent of the screen appearance.

The superseded LandingPage, wheel demo and unused Three.js hero were removed,
along with their unused Three.js dependencies. Existing backend workflows,
registration verification and account credit rules remain in place.

## Validation

```sh
npm ci
npm run build
npm run dev -- --port 3300
# In a second terminal:
npm run test:appearance
```

The appearance browser regression mocks account API responses. It checks themes,
persistence, local video, login routing and responsive navigation. The separate
`test:browser` command requires a running backend and an actual test account;
see the project README for setup.
