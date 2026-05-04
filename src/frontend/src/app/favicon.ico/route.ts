export function GET() {
  const svg = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <rect width="64" height="64" rx="14" fill="#111827"/>
  <path d="M18 34.5 28 44l18-24" fill="none" stroke="#67e8f9" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M18 18h28" fill="none" stroke="#93c5fd" stroke-width="4" stroke-linecap="round"/>
</svg>`;

  return new Response(svg.trim(), {
    headers: {
      "Content-Type": "image/svg+xml",
      "Cache-Control": "public, max-age=86400"
    }
  });
}
