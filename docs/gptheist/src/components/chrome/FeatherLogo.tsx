/** The desk's mark: a white feather on a green rounded square (inline SVG). */
export function FeatherLogo({ className = 'size-9' }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={`grid shrink-0 place-items-center rounded-[10px] bg-pos text-card ${className}`}
    >
      <svg viewBox="0 0 24 24" className="size-[62%]" fill="currentColor" aria-hidden="true">
        <path d="M20.5 3.2c-5.2-.6-10.1 1.2-13.7 4.8-3.4 3.4-5.3 8.1-5.3 12.9 0 .7.1 1.4.2 2l2.8-2.8c.4-3.5 1.9-6.7 4.3-9.1 2.1-2.1 4.8-3.6 7.7-4.3-2 1.9-3.7 4-4.9 6.4-1.7 3.3-2.7 6.9-2.7 10.6h3.5c.8-3.5 2.4-6.7 4.6-9.3 1.9-2.3 2.8-4.8 3.5-11.2z" />
      </svg>
    </span>
  );
}
