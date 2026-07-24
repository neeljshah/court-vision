"use client";

import { useEffect, useRef, useState } from "react";
import GlassCourtFallback from "./GlassCourtFallback";

// The Glass Court 3D hero. Home-only. Imported by the page via
//   next/dynamic(() => import("./GlassCourt"), { ssr: false })
// so `three` is zero bytes on every other route. On top of that page-level split
// this component adds a runtime gate: three is fetched (dynamic import) ONLY after
// the hero scrolls into view AND prefers-reduced-motion is no-preference AND a
// WebGL probe passes. Any failure keeps the static fallback -- the hero never
// looks broken. ponytail: no @types/three per rails ("three" dep ONLY); the
// `as any` specifier makes tsc treat the module as any (bundler still sees the
// literal), so the scene stays untyped rather than pulling a second dependency.

function webglOk(): boolean {
  try {
    const c = document.createElement("canvas");
    return !!(
      window.WebGLRenderingContext &&
      (c.getContext("webgl") || c.getContext("experimental-webgl"))
    );
  } catch {
    return false;
  }
}

function cssColor(el: Element, name: string, fallback: string): string {
  const v = getComputedStyle(el).getPropertyValue(name).trim();
  return v || fallback;
}

// Builds the scene into `wrap`, calls onLive() on the first rendered frame, and
// returns a disposer that tears down GL, geometry, listeners and the canvas.
function buildScene(
  THREE: any,
  wrap: HTMLDivElement,
  onLive: () => void
): () => void {
  const w = () => wrap.clientWidth || 1;
  const h = () => wrap.clientHeight || 1;

  const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setSize(w(), h());
  const canvas: HTMLCanvasElement = renderer.domElement;
  canvas.style.position = "absolute";
  canvas.style.inset = "0";
  canvas.style.width = "100%";
  canvas.style.height = "100%";
  canvas.style.borderRadius = "14px";
  canvas.style.display = "block";
  wrap.appendChild(canvas);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(30, w() / h(), 0.1, 100);
  camera.position.set(0, 1.5, 4.0); // low editorial angle (~21deg elevation)
  camera.lookAt(0, 0, 0);

  // soft ivory environment light -- no bloom, no glow
  const paper = new THREE.Color(cssColor(wrap, "--paper", "#FAF6EE"));
  const slate = new THREE.Color(cssColor(wrap, "--accent", "#1D5C7A"));
  const amber = new THREE.Color(cssColor(wrap, "--signal", "#C6852B"));
  scene.add(new THREE.HemisphereLight(0xfffdf5, 0xccbfa8, 1.05));
  const dir = new THREE.DirectionalLight(0xffffff, 0.5);
  dir.position.set(2, 4, 3);
  scene.add(dir);

  const group = new THREE.Group();
  scene.add(group);

  // thin translucent glass half-court plane on the XZ ground
  const glass = new THREE.Mesh(
    new THREE.PlaneGeometry(4, 3),
    new THREE.MeshStandardMaterial({
      color: paper,
      transparent: true,
      opacity: 0.16,
      roughness: 0.12,
      metalness: 0.0,
      side: THREE.DoubleSide,
    })
  );
  glass.rotation.x = -Math.PI / 2;
  group.add(glass);

  // slate wireframe court lines, floated a hair above the glass
  const y = 0.012;
  const lineMat = new THREE.LineBasicMaterial({
    color: slate,
    transparent: true,
    opacity: 0.5,
  });
  const seg = (pts: number[][]) =>
    new THREE.Line(
      new THREE.BufferGeometry().setFromPoints(
        pts.map((p) => new THREE.Vector3(p[0], y, p[1]))
      ),
      lineMat
    );
  group.add(
    seg([
      [-2, -1.5],
      [2, -1.5],
      [2, 1.5],
      [-2, 1.5],
      [-2, -1.5],
    ])
  ); // court border
  group.add(
    seg([
      [-0.7, -1.5],
      [-0.7, -0.25],
      [0.7, -0.25],
      [0.7, -1.5],
    ])
  ); // the key
  const circle: number[][] = [];
  for (let i = 0; i <= 48; i++) {
    const a = (i / 48) * Math.PI * 2;
    circle.push([Math.cos(a) * 0.55, Math.sin(a) * 0.55]);
  }
  group.add(seg(circle)); // center circle

  // the single amber arc -- draws in once on mount, then rests
  const curve = new THREE.EllipseCurve(
    0,
    -1.5,
    1.7,
    1.7,
    Math.PI * 0.13,
    Math.PI * 0.87,
    false,
    0
  );
  const arcPts = curve
    .getPoints(96)
    .map((p: any) => new THREE.Vector3(p.x, y + 0.002, p.y));
  const arcGeom = new THREE.BufferGeometry().setFromPoints(arcPts);
  arcGeom.setDrawRange(0, 0);
  group.add(
    new THREE.Line(
      arcGeom,
      new THREE.LineBasicMaterial({
        color: amber,
        transparent: true,
        opacity: 0.95,
      })
    )
  );
  const arcCount = arcPts.length;

  // pointer parallax state (camera yaw <= 4deg)
  const pointer = { x: 0, y: 0 };
  const onMove = (e: PointerEvent) => {
    const r = wrap.getBoundingClientRect();
    pointer.x = ((e.clientX - r.left) / r.width) * 2 - 1;
    pointer.y = ((e.clientY - r.top) / r.height) * 2 - 1;
  };
  const onLeave = () => {
    pointer.x = 0;
    pointer.y = 0;
  };
  wrap.addEventListener("pointermove", onMove);
  wrap.addEventListener("pointerleave", onLeave);

  const radius = Math.hypot(camera.position.x, camera.position.z);
  const baseAng = Math.atan2(camera.position.x, camera.position.z);
  const YAW = (4 * Math.PI) / 180;
  // cubic-bezier(.16,1,.3,1)-ish soft ease for the one-shot arc draw
  const ease = (t: number) => (t >= 1 ? 1 : 1 - Math.pow(2, -10 * t));
  const HERO_MS = 2400;

  let raf = 0;
  let first = true;
  const start = performance.now();
  const tick = (now: number) => {
    const t = (now - start) / 1000;
    const p = ease(Math.min((now - start) / HERO_MS, 1));
    arcGeom.setDrawRange(0, Math.max(1, Math.floor(arcCount * p)));
    // very slow idle drift
    group.rotation.y = 0.06 * Math.sin(t * 0.12);
    // eased pointer parallax on a small camera arc
    const ang = baseAng + pointer.x * YAW * 0.6;
    camera.position.x += (Math.sin(ang) * radius - camera.position.x) * 0.06;
    camera.position.z = Math.cos(ang) * radius;
    camera.position.y += (1.5 - pointer.y * 0.16 - camera.position.y) * 0.06;
    camera.lookAt(0, 0, 0);
    renderer.render(scene, camera);
    if (first) {
      first = false;
      onLive();
    }
    raf = requestAnimationFrame(tick);
  };
  raf = requestAnimationFrame(tick);

  const ro = new ResizeObserver(() => {
    renderer.setSize(w(), h());
    camera.aspect = w() / h();
    camera.updateProjectionMatrix();
  });
  ro.observe(wrap);

  return () => {
    cancelAnimationFrame(raf);
    ro.disconnect();
    wrap.removeEventListener("pointermove", onMove);
    wrap.removeEventListener("pointerleave", onLeave);
    scene.traverse((o: any) => {
      if (o.geometry) o.geometry.dispose();
      if (o.material) {
        (Array.isArray(o.material) ? o.material : [o.material]).forEach(
          (m: any) => m.dispose()
        );
      }
    });
    renderer.dispose();
    if (canvas.parentNode) canvas.parentNode.removeChild(canvas);
  };
}

export default function GlassCourt() {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [live, setLive] = useState(false);

  useEffect(() => {
    const wrap = wrapRef.current;
    if (!wrap) return;
    // gate 1: reduced motion -> never mount the 3D (checked once; a mid-session
    // preference flip keeps the still, which is the safe direction).
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    // gate 2: WebGL support
    if (!webglOk()) return;

    let disposed = false;
    let dispose: (() => void) | undefined;
    // gate 3: in view -> only now fetch three + build the scene
    const io = new IntersectionObserver(
      (entries) => {
        if (!entries.some((e) => e.isIntersecting)) return;
        io.disconnect();
        import("three" as any)
          .then((THREE: any) => {
            if (disposed || !wrapRef.current) return;
            dispose = buildScene(THREE, wrapRef.current, () => setLive(true));
          })
          .catch(() => {
            /* import failed -> keep the static fallback */
          });
      },
      { threshold: 0.25 }
    );
    io.observe(wrap);

    return () => {
      disposed = true;
      io.disconnect();
      dispose?.();
    };
  }, []);

  return (
    <div ref={wrapRef} style={{ position: "relative", width: "100%" }}>
      <GlassCourtFallback style={live ? { visibility: "hidden" } : undefined} />
    </div>
  );
}
