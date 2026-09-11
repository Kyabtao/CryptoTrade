import { useEffect, useState } from 'react';

const QUERY = '(prefers-reduced-motion: reduce)';

/**
 * True when the user asks for reduced motion. Animated visualisations
 * (penteract rotation, pulses) freeze to a static frame in that case, and CSS
 * backstops in index.css switch off decorative animation.
 */
function hasMatchMedia(): boolean {
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function';
}

export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState<boolean>(() =>
    hasMatchMedia() ? window.matchMedia(QUERY).matches : false
  );

  useEffect(() => {
    if (!hasMatchMedia()) return;
    const mq = window.matchMedia(QUERY);
    const onChange = () => {
      setReduced(mq.matches);
    };
    mq.addEventListener('change', onChange);
    return () => {
      mq.removeEventListener('change', onChange);
    };
  }, []);

  return reduced;
}
