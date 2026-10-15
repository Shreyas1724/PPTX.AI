# Works wheel UI integration

The existing app uses React 19, Vite, and strict TypeScript. Tailwind CSS 4, its PostCSS plugin, PostCSS, Autoprefixer, clsx, and tailwind-merge are now installed and recorded in the lockfile. No additional provider or global state manager is needed.

## Paths and shadcn conventions

- Reusable components: `frontend/src/components/ui/` (import as `@/components/ui`).
- Wheel: `frontend/src/components/ui/works-wheel.tsx`.
- Demo with nine Unsplash images: `frontend/src/components/ui/demo.tsx`.
- Class helper: `frontend/src/lib/utils.ts`.
- Tailwind styles and wheel tokens: `frontend/src/tailwind.css`.
- Existing application styles: `frontend/src/style.css`.

The old app kept page components directly in `src`. Creating `src/components/ui` separates reusable primitives from application pages and gives shadcn CLI and copied components a consistent import destination. In this Vite project, `/components/ui` means the source-root folder resolved by `@`, not a server URL or a filesystem-root directory. Both TypeScript and Vite resolve the alias. `components.json` records these conventions for shadcn CLI.

## Install and extend

The setup is already complete. In `frontend`, run:

```sh
npm ci
npm run dev
npm run build
# Add future shadcn components using the existing configuration:
npx shadcn@latest add button
```

For a new Vite TypeScript project, install Tailwind 4, @tailwindcss/postcss, PostCSS, Autoprefixer, clsx and tailwind-merge; add the Tailwind/PostCSS configuration and `@` alias; then run `npx shadcn@latest init` and choose `src/components/ui` and the global CSS file. Do not run init over this project's existing configuration unnecessarily.

Tailwind preflight is intentionally omitted from `src/tailwind.css` to preserve existing auth/editor styling. Utilities still compile normally. Wheel color tokens are scoped to `.works-wheel`; backend, auth, credit behavior, and other pages are unchanged.

## Product placement and behavior

The homepage uses the supplied ring-to-drum interaction beneath its existing hero. Cards link to `/create`; users who need to sign in encounter the existing auth flow. The images are inspirational stock art, not saved user presentations. Replace the `WORKS` array to use actual covers and deck links. The nginx image policy allows the Unsplash host.

The component keeps transform animation in requestAnimationFrame and only the active index and measured stage in React state. It supports scroll, vertical drag, ArrowUp/ArrowDown, Home/End, click-to-select titles, reduced motion, pointer cancellation, instance-safe IDs, and bounds when the item count changes. Desktop and mobile stage heights are bounded; page scrolling resumes at either end of the wheel. Lucide supplies the card action icon. Each item accepts `title`, `image`, and optional `href`; section props, `label`, `action`, and `className` are exposed.

## Validation

TypeScript and Vite production build pass. The wheel includes a minimum stage height and responsive index text. Unsplash assets require internet access. Nine bundled SVG covers provide a deliberate visual fallback when remote images are blocked. Desktop/mobile browser checks passed with no page errors or horizontal overflow; arrow keys advanced the selected slide.

## Repository integration validation

The supplied frontend source and bundled wheel covers are integrated under the repository root. TypeScript and the Vite production build pass with Tailwind 4; `npm audit` reports zero vulnerabilities. The existing theme configuration is loaded using `@config`; the theme and utilities imports omit preflight to preserve application styling. Browser checks described above are historical and were not repeated during this integration.
