"use client";

import dynamic from "next/dynamic";
import { Component, useEffect, useState } from "react";
import type { ReactNode } from "react";

const FloatingLines = dynamic(() => import("./floating-lines"), {ssr: false});

const floatingLinesGradient = ["#45aec8", "#4446b8", "#c7bebe"];
const floatingLinesWaves = ["top", "middle", "bottom"] as const;
const floatingLinesDistance = [8, 8, 8];

class BackgroundBoundary extends Component<{children: ReactNode}, {failed: boolean}> {
  state = {failed: false};
  static getDerivedStateFromError() { return {failed: true}; }
  render() { return this.state.failed ? null : this.props.children; }
}

export default function FloatingLinesBackground() {
  const [supported, setSupported] = useState(false);
  const [reduced, setReduced] = useState(true);
  const [visible, setVisible] = useState(true);
  const [paused, setPaused] = useState(false);

  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const syncMotion = () => setReduced(media.matches);
    const syncVisibility = () => setVisible(!document.hidden);
    syncMotion();
    syncVisibility();
    media.addEventListener("change", syncMotion);
    document.addEventListener("visibilitychange", syncVisibility);
    try {
      const canvas = document.createElement("canvas");
      const context = canvas.getContext("webgl2") || canvas.getContext("webgl");
      setSupported(Boolean(context));
      context?.getExtension("WEBGL_lose_context")?.loseContext();
    } catch {
      setSupported(false);
    }
    return () => {
      media.removeEventListener("change", syncMotion);
      document.removeEventListener("visibilitychange", syncVisibility);
    };
  }, []);

  const active = supported && !reduced && visible && !paused;
  return <>
    <div className="floating-lines-background" data-floating-lines-background data-active={active} aria-hidden="true">
      {active && <BackgroundBoundary><FloatingLines
        linesGradient={floatingLinesGradient}
        enabledWaves={floatingLinesWaves}
        lineCount={8}
        lineDistance={floatingLinesDistance}
        animationSpeed={1}
        interactive
        bendRadius={15}
        bendStrength={-2}
        mouseDamping={0.06}
        parallax
        parallaxStrength={0.18}
        mixBlendMode="screen"
        backgroundColor="#080808"
      /></BackgroundBoundary>}
    </div>
    {supported && !reduced && <button
      type="button"
      className="background-toggle"
      aria-label={paused ? "배경 움직임 켜기" : "배경 움직임 끄기"}
      aria-pressed={!paused}
      onClick={() => setPaused(value => !value)}
    >
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
        {paused ? <path d="m5 3 7 5-7 5Z"/> : <path d="M5 3v10M11 3v10"/>}
      </svg>
      배경 모션 {paused ? "끔" : "켬"}
    </button>}
  </>;
}
