"use client";
// The isometric line drawing. Loaded only on the client (next/dynamic, ssr: false). Orthographic camera at the true
// isometric angle, flat paper faces, thin ink edges, demand rendering; nothing moves unless the reader moves it (the
// preview may settle once on arrival, never with reduced motion).
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, type RefObject } from "react";
import * as THREE from "three";
import { Canvas, useFrame, useThree, type ThreeEvent } from "@react-three/fiber";
import { Edges, Line, OrbitControls } from "@react-three/drei";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";
import type { Verdict } from "@/lib/types";
import { SIZE, type Drawing, type Part } from "./layout";
import type { ProjStore, ViewApi } from "./store";
import type { Tokens } from "./useTokens";

export interface SceneProps {
  drawing: Drawing;
  parts: Part[];
  verdict: Verdict;
  tokens: Tokens;
  active: Set<string> | null;
  onHover: (key: string | null) => void;
  onPick: (key: string) => void;
  store: ProjStore;
  viewRef: RefObject<ViewApi | null>;
  orbit: boolean;
  reduced: boolean;
  pad: { x: number; top: number; bottom: number };
  onReady: () => void;
  /** Hover and click on parts (off in the static preview). */
  interactive?: boolean;
  /** A gentle one-time settle of the camera on mount (preview only; ignored with reduced motion). */
  settle?: boolean;
}

const ISO_AZ = Math.PI / 4;
const ISO_POLAR = Math.acos(1 / Math.sqrt(3));
const LIMIT = (25 * Math.PI) / 180;
const ISO_DIR = new THREE.Vector3(1, 1, 1).normalize();

/** Colours of the drawing, all derived from the tokens. */
interface Palette {
  line: THREE.Color; ground: THREE.Color; muted: THREE.Color; guide: THREE.Color; grid: THREE.Color;
  accent: THREE.Color; holds: THREE.Color; disputed: THREE.Color;
  faces: THREE.MeshBasicMaterial[]; accentFaces: THREE.MeshBasicMaterial[];
}

function usePalette(t: Tokens): Palette {
  const pal = useMemo(() => {
    const c = (s: string) => new THREE.Color(s);
    const ground = c(t.ground), line = c(t.line);
    const mix = (a: THREE.Color, b: THREE.Color, k: number) => a.clone().lerp(b, k);
    const top = t.dark ? mix(ground, line, 0.07) : mix(ground, c("#ffffff"), 0.55);
    const sideA = mix(ground, line, t.dark ? 0.03 : 0.06);
    const sideB = mix(ground, line, t.dark ? 0.11 : 0.13);
    const accent = c(t.accent);
    const mat = (col: THREE.Color) => new THREE.MeshBasicMaterial({ color: col, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 });
    // BoxGeometry groups: +x, -x, +y, -y, +z, -z. The camera sees +x, +y and +z.
    const set = (topC: THREE.Color) => [mat(sideA), mat(sideB), mat(topC), mat(sideB), mat(sideB), mat(sideA)];
    return {
      line, ground, accent, holds: c(t.holds), disputed: c(t.disputed),
      muted: c(t.ink3), guide: mix(ground, line, t.dark ? 0.26 : 0.28), grid: mix(ground, line, t.dark ? 0.055 : 0.08),
      faces: set(top), accentFaces: set(mix(top, accent, t.dark ? 0.13 : 0.12)),
    };
  }, [t]);
  useEffect(() => () => { [...pal.faces, ...pal.accentFaces].forEach(m => m.dispose()); }, [pal]);
  return pal;
}

const half = (p: Part) => (p.kind === "decision" ? SIZE.base / 2 : p.kind === "premise" ? SIZE.tile / 2 : Math.max(SIZE.slabW, SIZE.slabD) / 2);
const topY = (p: Part) => (p.kind === "decision" ? SIZE.baseH + SIZE.plinthH : p.kind === "premise" ? SIZE.tileH : SIZE.slabH);

/** Edge colour and dash for a part, from its premise state or evidence relation. */
function stroke(p: Part, pal: Palette, verdict: Verdict): { color: THREE.Color; dashed: boolean; accent: boolean } {
  if (p.kind === "evidence") return p.rel === "CONTRADICTS" ? { color: pal.accent, dashed: false, accent: true } : { color: pal.holds, dashed: false, accent: false };
  if (p.kind === "decision") return { color: pal.line, dashed: verdict === "NOT_YET", accent: false };
  switch (p.state) {
    case "expired": return { color: pal.accent, dashed: false, accent: true };
    case "disputed": return { color: pal.disputed, dashed: false, accent: false };
    case "unchecked": case "unevidenced": return { color: pal.muted, dashed: true, accent: false };
    default: return { color: pal.line, dashed: false, accent: false };
  }
}

interface Look { color: THREE.Color; width: number; dashed: boolean }

function Block({ size, position, look, faces, rotationZ = 0, handlers }: {
  size: [number, number, number]; position: [number, number, number]; look: Look; faces: THREE.Material[]; rotationZ?: number;
  handlers?: Partial<Record<"onPointerOver" | "onPointerOut" | "onClick", (e: ThreeEvent<PointerEvent | MouseEvent>) => void>>;
}) {
  const [w, h, d] = size;
  const geo = useMemo(() => new THREE.BoxGeometry(w, h, d), [w, h, d]);
  useEffect(() => () => geo.dispose(), [geo]);
  return (
    <mesh geometry={geo} position={position} rotation={[0, 0, rotationZ]} material={faces} {...handlers}>
      <Edges color={look.color} lineWidth={look.width} dashed={look.dashed} dashSize={0.11} gapSize={0.08} />
    </mesh>
  );
}

/** A flat cable on the ground from a part to the part it plugs into. Unplugged: a gap, the plug end lifted. */
function Cable({ child, parent, look, unplugged, faces, accentFaces }: {
  child: Part; parent: Part; look: Look; unplugged: boolean; faces: THREE.Material[]; accentFaces: THREE.Material[];
}) {
  const dx = parent.x - child.x, dz = parent.z - child.z;
  const dist = Math.hypot(dx, dz) || 1;
  const ux = dx / dist, uz = dz / dist;
  const exit = (p: Part) => (p.kind === "evidence" ? half(p) * 0.8 : half(p) / Math.max(Math.abs(ux), Math.abs(uz)));
  const a = exit(child), b = exit(parent);
  const L = Math.max(0.4, dist - a - b);
  const sx = child.x + ux * a, sz = child.z + uz * a;
  const rotY = Math.atan2(-uz, ux);
  const { cableW: cw, cableH: ch } = SIZE;
  if (!unplugged) {
    return (
      <group position={[sx, 0.01, sz]} rotation={[0, rotY, 0]}>
        <Block size={[L, ch, cw]} position={[L / 2, ch / 2, 0]} look={look} faces={faces} />
      </group>
    );
  }
  const L1 = L * 0.3, rise = 0.75, phi = 0.95, plug = 0.34;
  const cx = Math.cos(phi), sy = Math.sin(phi);
  return (
    <group position={[sx, 0.01, sz]} rotation={[0, rotY, 0]}>
      <Block size={[L1, ch, cw]} position={[L1 / 2, ch / 2, 0]} look={look} faces={faces} />
      <Block size={[rise, ch, cw]} position={[L1 + (cx * rise) / 2, (sy * rise) / 2 + ch / 2, 0]} rotationZ={phi} look={look} faces={faces} />
      <Block size={[plug, 0.2, 0.32]} position={[L1 + cx * (rise + plug / 2), sy * (rise + plug / 2) + ch / 2, 0]} rotationZ={phi}
        look={{ ...look, width: look.width + 0.3 }} faces={accentFaces} />
      {/* the empty socket on the parent side */}
      <Block size={[0.42, 0.04, 0.42]} position={[L - 0.26, 0.02, 0]} look={{ ...look, dashed: true }} faces={faces} />
    </group>
  );
}

function Grid({ bounds, color }: { bounds: Drawing["bounds"]; color: THREE.Color }) {
  const geo = useMemo(() => {
    const m = 16, step = 1;
    const x0 = Math.floor(bounds.minX - m), x1 = Math.ceil(bounds.maxX + m);
    const z0 = Math.floor(bounds.minZ - m), z1 = Math.ceil(bounds.maxZ + m);
    const v: number[] = [];
    for (let x = x0; x <= x1; x += step) v.push(x, 0, z0, x, 0, z1);
    for (let z = z0; z <= z1; z += step) v.push(x0, 0, z, x1, 0, z);
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(v, 3));
    return g;
  }, [bounds]);
  useEffect(() => () => geo.dispose(), [geo]);
  return <lineSegments geometry={geo}><lineBasicMaterial color={color} /></lineSegments>;
}

function Arc({ r, from, to, color }: { r: number; from: number; to: number; color: THREE.Color }) {
  const pts = useMemo(() => {
    const n = Math.max(12, Math.ceil(((to - from) * r) / 0.3));
    return Array.from({ length: n + 1 }, (_, i) => {
      const a = from + ((to - from) * i) / n;
      return new THREE.Vector3(Math.cos(a) * r, 0.002, -Math.sin(a) * r);
    });
  }, [r, from, to]);
  return <Line points={pts} color={color} lineWidth={1} dashed dashSize={0.22} gapSize={0.18} />;
}

/** Fits the drawing in the canvas at the isometric angle; owns reset and zoom; limits the orbit. */
const Y_AXIS = new THREE.Vector3(0, 1, 0);
const SETTLE_MS = 1100;
const SETTLE_TURN = (-9 * Math.PI) / 180;

function Rig({ footprints, viewRef, orbit, reduced, pad, settle }: Pick<SceneProps, "viewRef" | "orbit" | "reduced" | "pad" | "settle"> & { footprints: Drawing["footprints"] }) {
  const camera = useThree(s => s.camera) as THREE.OrthographicCamera;
  const size = useThree(s => s.size);
  const invalidate = useThree(s => s.invalidate);
  const controls = useRef<OrbitControlsImpl>(null);
  const settleFrom = useRef<number | null>(null);
  const settled = useRef(false);
  const aim = useRef(new THREE.Vector3());

  const fit = useMemo(() => {
    const cam = new THREE.OrthographicCamera();
    cam.position.copy(ISO_DIR).multiplyScalar(60);
    cam.lookAt(0, 0, 0);
    cam.updateMatrixWorld();
    const inv = cam.matrixWorldInverse;
    const v = new THREE.Vector3();
    let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
    const H = SIZE.baseH + SIZE.plinthH;
    for (const f of footprints) for (const dx of [-f.e, f.e]) for (const dz of [-f.e, f.e]) for (const y of [0, H]) {
      v.set(f.x + dx, y, f.z + dz).applyMatrix4(inv);
      x0 = Math.min(x0, v.x); x1 = Math.max(x1, v.x); y0 = Math.min(y0, v.y); y1 = Math.max(y1, v.y);
    }
    const right = new THREE.Vector3().setFromMatrixColumn(cam.matrixWorld, 0);
    const up = new THREE.Vector3().setFromMatrixColumn(cam.matrixWorld, 1);
    const target = right.multiplyScalar((x0 + x1) / 2).add(up.multiplyScalar((y0 + y1) / 2));
    return { target, spanX: x1 - x0, spanY: y1 - y0 };
  }, [footprints]);

  // Never larger than ~55 px per unit, so a lone module does not fill the sheet.
  const base = Math.max(8, Math.min(55, (size.width - pad.x * 2) / fit.spanX, (size.height - pad.top - pad.bottom) / fit.spanY));
  // Shift the target so the drawing sits between the top and bottom padding.
  const shiftY = (pad.top - pad.bottom) / 2 / base;

  const reset = useCallback(() => {
    const up = new THREE.Vector3(-1, 2, -1).normalize(); // screen-up at the isometric angle
    const t = fit.target.clone().addScaledVector(up, shiftY);
    aim.current.copy(t);
    camera.position.copy(t).addScaledVector(ISO_DIR, 60);
    camera.up.set(0, 1, 0);
    camera.lookAt(t);
    camera.zoom = base;
    camera.updateProjectionMatrix();
    if (controls.current) { controls.current.target.copy(t); controls.current.update(); }
    invalidate();
  }, [camera, fit, base, shiftY, invalidate]);

  useLayoutEffect(() => {
    reset();
    if (settle && !reduced && !settled.current) { settled.current = true; settleFrom.current = performance.now(); invalidate(); }
  }, [reset, settle, reduced, invalidate]);

  // The one-time settle: a few degrees of turn and a little zoom, easing into the isometric view.
  useFrame(() => {
    if (settleFrom.current === null) return;
    const k = Math.min(1, (performance.now() - settleFrom.current) / SETTLE_MS);
    const e = 1 - Math.pow(1 - k, 3);
    const dir = ISO_DIR.clone().applyAxisAngle(Y_AXIS, SETTLE_TURN * (1 - e));
    camera.position.copy(aim.current).addScaledVector(dir, 60);
    camera.lookAt(aim.current);
    camera.zoom = base * (0.93 + 0.07 * e);
    camera.updateProjectionMatrix();
    if (k < 1) invalidate(); else settleFrom.current = null;
  });
  useEffect(() => {
    viewRef.current = {
      reset,
      zoomBy: f => {
        camera.zoom = THREE.MathUtils.clamp(camera.zoom * f, base * 0.7, base * 2.6);
        camera.updateProjectionMatrix();
        invalidate();
      },
    };
    return () => { viewRef.current = null; };
  }, [reset, camera, base, invalidate, viewRef]);

  if (!orbit) return null;
  return (
    <OrbitControls ref={controls} makeDefault enablePan={false} enableZoom={false} enableDamping={!reduced} dampingFactor={0.12}
      minAzimuthAngle={ISO_AZ - LIMIT} maxAzimuthAngle={ISO_AZ + LIMIT}
      minPolarAngle={ISO_POLAR - LIMIT} maxPolarAngle={ISO_POLAR + LIMIT} />
  );
}

/** Projects each part's top centre (and the ring label points) to canvas pixels for the HTML callouts. */
function Projector({ anchors, store }: { anchors: { key: string; v: THREE.Vector3 }[]; store: ProjStore }) {
  const camera = useThree(s => s.camera);
  const size = useThree(s => s.size);
  const invalidate = useThree(s => s.invalidate);
  const tmp = useMemo(() => new THREE.Vector3(), []);
  const last = useRef<Float32Array>(new Float32Array(0));
  useEffect(() => { last.current = new Float32Array(0); invalidate(); }, [anchors, invalidate]);
  useFrame(() => {
    const n = anchors.length;
    if (last.current.length !== n * 2 + 3) last.current = new Float32Array(n * 2 + 3).fill(NaN);
    const buf = last.current;
    const zoom = (camera as THREE.OrthographicCamera).zoom;
    let changed = buf[n * 2] !== size.width || buf[n * 2 + 1] !== size.height || buf[n * 2 + 2] !== zoom;
    for (let i = 0; i < n; i++) {
      tmp.copy(anchors[i].v).project(camera);
      const x = ((tmp.x + 1) / 2) * size.width, y = ((1 - tmp.y) / 2) * size.height;
      if (!(Math.abs(buf[i * 2] - x) < 0.5 && Math.abs(buf[i * 2 + 1] - y) < 0.5)) changed = true;
      buf[i * 2] = x; buf[i * 2 + 1] = y;
    }
    if (!changed) return;
    buf[n * 2] = size.width; buf[n * 2 + 1] = size.height; buf[n * 2 + 2] = zoom;
    const pts: Record<string, [number, number]> = {};
    anchors.forEach((a, i) => { pts[a.key] = [buf[i * 2], buf[i * 2 + 1]]; });
    store.set({ w: size.width, h: size.height, zoom, pts });
  });
  return null;
}

function Drawn({ drawing, parts, verdict, active, onHover, onPick, pal, interactive = true }: Pick<SceneProps, "drawing" | "parts" | "verdict" | "active" | "onHover" | "onPick" | "interactive"> & { pal: Palette }) {
  const byKey = useMemo(() => new Map(drawing.parts.map(p => [p.key, p])), [drawing]);
  const dim = useCallback((c: THREE.Color, key: string) => (active && !active.has(key) ? c.clone().lerp(pal.ground, 0.62) : c), [active, pal]);
  const width = (key: string) => (active?.has(key) ? 2.2 : 1.25);
  const gl = useThree(s => s.gl);
  const handlers = (key: string) => (!interactive ? undefined : {
    onPointerOver: (e: ThreeEvent<PointerEvent | MouseEvent>) => { e.stopPropagation(); onHover(key); gl.domElement.style.cursor = "pointer"; },
    onPointerOut: () => { onHover(null); gl.domElement.style.cursor = ""; },
    onClick: (e: ThreeEvent<PointerEvent | MouseEvent>) => { e.stopPropagation(); onPick(key); },
  });

  return (
    <group>
      {parts.map(p => {
        const s = stroke(p, pal, verdict);
        const look: Look = { color: dim(s.color, p.key), width: width(p.key), dashed: s.dashed };
        const faces = s.accent ? pal.accentFaces : pal.faces;
        const h = handlers(p.key);
        const parent = p.parent ? byKey.get(p.parent) : null;
        const cable = parent && (
          <Cable key={`c-${p.key}`} child={p} parent={parent} look={look} faces={pal.faces} accentFaces={pal.accentFaces}
            unplugged={p.kind === "premise" && p.state === "expired"} />
        );
        if (p.kind === "decision") {
          const inset = verdict === "MOOT" ? pal.accent : pal.line;
          return (
            <group key={p.key}>
              <Block size={[SIZE.base, SIZE.baseH, SIZE.base]} position={[0, SIZE.baseH / 2, 0]} look={look} faces={pal.faces} handlers={h} />
              <Block size={[SIZE.plinth, SIZE.plinthH, SIZE.plinth]} position={[0, SIZE.baseH + SIZE.plinthH / 2, 0]} look={look} faces={pal.faces} handlers={h} />
              <Block size={[SIZE.plinth * 0.68, 0.035, SIZE.plinth * 0.68]} position={[0, SIZE.baseH + SIZE.plinthH + 0.018, 0]}
                look={{ ...look, color: dim(inset, p.key) }} faces={verdict === "MOOT" ? pal.accentFaces : pal.faces} handlers={h} />
            </group>
          );
        }
        if (p.kind === "premise") {
          return (
            <group key={p.key}>
              {cable}
              <Block size={[SIZE.tile, SIZE.tileH, SIZE.tile]} position={[p.x, SIZE.tileH / 2, p.z]} look={look} faces={faces} handlers={h} />
              <Block size={[SIZE.tile * 0.62, 0.03, SIZE.tile * 0.62]} position={[p.x, SIZE.tileH + 0.015, p.z]} look={{ ...look, width: 1 }} faces={faces} />
            </group>
          );
        }
        return (
          <group key={p.key}>
            {cable}
            <Block size={[SIZE.slabW, SIZE.slabH, SIZE.slabD]} position={[p.x, SIZE.slabH / 2, p.z]} look={look} faces={faces} handlers={h} />
          </group>
        );
      })}
    </group>
  );
}

export default function IsoScene(props: SceneProps) {
  const { drawing, parts, tokens, store, viewRef, orbit, reduced, pad, onReady, onHover, settle } = props;
  const pal = usePalette(tokens);
  const anchors = useMemo(() => [
    ...parts.map(p => ({ key: p.key, v: new THREE.Vector3(p.x, topY(p), p.z) })),
    ...drawing.rings.map(r => ({ key: `ring:${r.label}`, v: new THREE.Vector3(Math.cos(r.to) * r.r, 0, -Math.sin(r.to) * r.r) })),
  ], [parts, drawing]);

  return (
    <Canvas orthographic flat frameloop="demand" dpr={[1, 2]} gl={{ antialias: true, alpha: true }}
      camera={{ position: [60, 60, 60], zoom: 40, near: 0.1, far: 400 }}
      onCreated={({ gl }) => { gl.setClearColor(0x000000, 0); onReady(); }}
      onPointerMissed={() => onHover(null)} aria-hidden="true">
      <Rig footprints={drawing.footprints} viewRef={viewRef} orbit={orbit} reduced={reduced} pad={pad} settle={settle} />
      <Grid bounds={drawing.bounds} color={pal.grid} />
      {drawing.rings.map(r => <Arc key={r.label} r={r.r} from={r.from} to={r.to} color={pal.guide} />)}
      <Drawn {...props} pal={pal} />
      <Projector anchors={anchors} store={store} />
    </Canvas>
  );
}
