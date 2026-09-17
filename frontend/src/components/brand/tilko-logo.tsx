"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import { useSecretAdminTap } from "@/components/brand/secret-admin-tap";
import foxLogo from "./tilko-fox.png";

const foxSrc = typeof foxLogo === "string" ? foxLogo : foxLogo.src;

function Mark({ size }: { size: number }) {
  return (
    <svg
      viewBox="0 0 32 32"
      width={Math.round(size * 0.62)}
      height={Math.round(size * 0.62)}
      fill="none"
      aria-hidden
    >
      <path
        d="M6 26V8h6.2l3.8 7.4L19.8 8H26v18h-5.2V15.2L17.2 22h-2.4l-3.6-6.8V26H6Z"
        fill="currentColor"
      />
      <path d="M9.2 4.5 16 10.8 22.8 4.5 16 1.8 9.2 4.5Z" fill="currentColor" />
    </svg>
  );
}

export function TilkoLogo({
  className,
  size = 36,
}: {
  className?: string;
  size?: number;
}) {
  const [broken, setBroken] = useState(false);
  const openAdmin = useSecretAdminTap();

  return (
    <span
      className={cn(
        "inline-flex select-none items-center justify-center overflow-hidden rounded-xl bg-zinc-950",
        broken ? "bg-cyan-400 text-zinc-950 shadow-neon" : null,
        className,
      )}
      style={{ width: size, height: size }}
      onClick={openAdmin}
    >
      {broken ? (
        <Mark size={size} />
      ) : (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={foxSrc}
          alt="TİLKO"
          width={size}
          height={size}
          className="h-full w-full object-contain"
          onError={() => setBroken(true)}
        />
      )}
    </span>
  );
}

export function TilkoWordmark({ className }: { className?: string }) {
  return (
    <span className={cn("font-semibold tracking-tight", className)}>TİLKO</span>
  );
}
