"use client";

import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

// A demo clip in a browser-window frame. Plays only while on screen.
// With reduced motion it never autoplays: the poster shows with native controls.
export function DemoVideo({ name, label, className }: { name: string; label: string; className?: string }) {
  const frame = useRef<HTMLDivElement>(null);
  const video = useRef<HTMLVideoElement>(null);
  const [shown, setShown] = useState(false);

  useEffect(() => {
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) {
      video.current!.controls = true;
      return; // no setShown needed: .rise only hides the frame under no-preference (globals.css)
    }
    const io = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) {
        setShown(true);
        video.current?.play().catch(() => {});
      } else {
        video.current?.pause();
      }
    }, { threshold: 0.4 });
    io.observe(frame.current!);
    return () => io.disconnect();
  }, []);

  return (
    <div ref={frame} data-shown={shown || undefined}
      className={cn("rise overflow-hidden rounded-xl border bg-card shadow-[0_18px_40px_-18px_rgba(17,24,39,0.35)]", className)}>
      <div className="flex gap-1.5 border-b bg-background px-4 py-3" aria-hidden>
        <span className="size-2.5 rounded-full bg-[#E3E6EB]" />
        <span className="size-2.5 rounded-full bg-[#E3E6EB]" />
        <span className="size-2.5 rounded-full bg-[#E3E6EB]" />
      </div>
      <video ref={video} muted playsInline loop preload="none" poster={`/clips/${name}-poster.jpg`}
        aria-label={label} className="block aspect-[16/10] w-full bg-background">
        <source src={`/clips/${name}.webm`} type="video/webm" />
        <source src={`/clips/${name}.mp4`} type="video/mp4" />
      </video>
    </div>
  );
}
