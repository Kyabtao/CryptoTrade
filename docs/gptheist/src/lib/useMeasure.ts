import { useEffect, useRef, useState } from 'react';

export type Measure = { width: number; height: number };

/**
 * Observe an element's content box so SVG visualisations can size themselves to
 * their card. Returns a ref to attach and the last measured size.
 *
 * Charts must not render until width is known, otherwise D3 scales divide by
 * zero on the first paint.
 */
export function useMeasure<T extends HTMLElement>() {
  const ref = useRef<T | null>(null);
  const [size, setSize] = useState<Measure>({ width: 0, height: 0 });

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const read = () => {
      const rect = el.getBoundingClientRect();
      setSize((prev) =>
        prev.width === rect.width && prev.height === rect.height
          ? prev
          : { width: rect.width, height: rect.height }
      );
    };

    read();
    // jsdom (tests) has no ResizeObserver; a single read is enough there.
    if (typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(read);
    ro.observe(el);
    return () => {
      ro.disconnect();
    };
  }, []);

  return [ref, size] as const;
}
