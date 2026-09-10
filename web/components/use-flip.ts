"use client";

import { useLayoutEffect, useRef } from "react";

/** FLIP list animation: measure, invert, play on order changes. */
export function useFlip(dependency: unknown) {
  const elements = useRef(new Map<string, HTMLElement>());
  const previous = useRef(new Map<string, DOMRect>());

  useLayoutEffect(() => {
    const current = new Map<string, DOMRect>();
    elements.current.forEach((element, key) => {
      current.set(key, element.getBoundingClientRect());
    });
    elements.current.forEach((element, key) => {
      const before = previous.current.get(key);
      const after = current.get(key);
      if (!before || !after) return;
      const dy = before.top - after.top;
      if (Math.abs(dy) < 1) return;
      element.style.transition = "none";
      element.style.transform = `translateY(${dy}px)`;
      requestAnimationFrame(() => {
        element.style.transition =
          "transform 0.55s cubic-bezier(0.2, 0.7, 0.3, 1)";
        element.style.transform = "";
      });
    });
    previous.current = current;
  }, [dependency]);

  return (key: string) => (element: HTMLElement | null) => {
    if (element) {
      elements.current.set(key, element);
    } else {
      elements.current.delete(key);
    }
  };
}
