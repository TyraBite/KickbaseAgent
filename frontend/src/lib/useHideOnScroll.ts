import { useEffect, useRef, useState } from "react";

const SCROLL_DELTA_THRESHOLD = 4;

export function nextHeaderVisible(previousY: number, currentY: number, wasVisible: boolean): boolean {
  if (currentY <= 0) return true;
  const delta = currentY - previousY;
  if (delta > SCROLL_DELTA_THRESHOLD) return false;
  if (delta < -SCROLL_DELTA_THRESHOLD) return true;
  return wasVisible;
}

export function useHideOnScroll(): boolean {
  const [visible, setVisible] = useState(true);
  const lastY = useRef(0);

  useEffect(() => {
    lastY.current = window.scrollY;
    function onScroll() {
      const currentY = window.scrollY;
      setVisible((prev) => nextHeaderVisible(lastY.current, currentY, prev));
      lastY.current = currentY;
    }
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return visible;
}
