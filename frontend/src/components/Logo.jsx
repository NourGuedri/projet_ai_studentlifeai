"use client";
import { useState } from "react";

const SHOW_NAME = true;

export default function Logo({ className = "h-19 w-auto max-w-[15rem]" }) {
  const [missing, setMissing] = useState(false);
  return (
    <span className="flex items-center gap-2.5">
      <span className="flex shrink-0 items-center justify-center">
        {missing ? (
          <span className="flex h-8 w-8 items-center justify-center rounded-md bg-leaf-500 font-display text-lg font-bold text-white">S</span>
        ) : (
          // eslint-disable-next-line @next/next/no-img-element
          <img src="/logo.png" alt="StudentLife AI" className={className} onError={() => setMissing(true)} />
        )}
      </span>
      {SHOW_NAME && <span className="font-display text-xl font-semibold text-white">StudentLife AI</span>}
    </span>
  );
}
