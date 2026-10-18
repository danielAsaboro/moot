"use client";
// The ruled-ledger field in 3D: ruled paper seen from a fixed axonometric angle, one line-drawn token per
// Larkspur decision. Tokens rest above the line while their reasons hold and sink below it, in accent, when
// the timeline lists them as moot. Renders on demand (no ambient motion): frames run only while a token moves.
// Loaded client-only through next/dynamic; HeroField shows a 2D fallback first.
import { useRouter } from "next/navigation";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import * as THREE from "three";
import { useEffect, useMemo, useRef, useState } from "react";
import s from "./Hero.module.css";
import { usePalette, type Palette } from "./HeroHooks";
import { decisionHref, type FieldToken, type TokenState } from "./HeroModel";

const SX = 2.1, SZ = 2.4;                 // token pitch along a ruled row / between rows
const TW = 1.3, TH = 0.46, TD = 0.86;     // token size
const FLOAT_Y = 0.34 + TH / 2;            // afloat: bottom a little above the paper
const SINK_Y = 0.12 - TH / 2;             // sunk: only the top shows above the line
const AZ = THREE.MathUtils.degToRad(15), EL = THREE.MathUtils.degToRad(30);
const CAM_DIR = new THREE.Vector3(Math.sin(AZ) * Math.cos(EL), Math.sin(EL), Math.cos(AZ) * Math.cos(EL));

let edgeGeo: THREE.EdgesGeometry | null = null;
const tokenEdges = () => (edgeGeo ??= new THREE.EdgesGeometry(new THREE.BoxGeometry(TW, TH, TD)));

export interface Field3DProps {
  tokens: FieldToken[]; states: TokenState[]; cols: number; rows: number; asOf: string;
  reduced: boolean; active: boolean; showAllLabels: boolean; onReady: () => void;
}

type Reg = Map<string, THREE.Group>;

export default function HeroField3D(p: Field3DProps) {
  const pal = usePalette();
  const [hover, setHover] = useState<string | null>(null);
  const groups = useRef<Reg>(new Map());
  const labels = useRef<Map<string, HTMLSpanElement>>(new Map());
  const router = useRouter();
  if (!pal) return null;
  return (
    <>
      <Canvas
        orthographic flat dpr={[1, 2]}
        frameloop="demand"
        gl={{ antialias: true, alpha: true }}
        camera={{ position: [30, 20, 50], zoom: 40, near: 0.1, far: 300 }}
        onCreated={() => p.onReady()}
      >
        <Scene
          {...p} pal={pal} hover={hover} setHover={setHover} groups={groups.current} labels={labels.current}
          open={id => router.push(decisionHref(id, p.asOf))}
        />
      </Canvas>
      {/* Token ids, positioned each frame from the projected token positions. */}
      <div className={s.labels} aria-hidden="true">
        {p.tokens.map((t, i) => {
          const st = p.states[i], on = hover === t.id;
          const show = p.showAllLabels || st === "moot" || on;
          return (
            <span
              key={t.id}
              ref={el => { if (el) labels.current.set(t.id, el); else labels.current.delete(t.id); }}
              className={`${s.tokLabel} ${st === "moot" ? s.tokMoot : ""} ${st === "ghost" ? s.tokGhost : ""} ${on ? s.tokHover : ""} ${show ? "" : s.tokHidden}`}
            >
              {t.id}{on && <span className={s.tokTitle}> · {t.title}</span>}
            </span>
          );
        })}
      </div>
    </>
  );
}

interface SceneProps extends Field3DProps {
  pal: Palette; hover: string | null; setHover: (f: (h: string | null) => string | null) => void;
  groups: Reg; labels: Map<string, HTMLSpanElement>; open: (id: string) => void;
}

function Scene({ tokens, states, cols, rows, reduced, active, pal, hover, setHover, groups, labels, open }: SceneProps) {
  const halfW = ((cols - 1) * SX) / 2, halfD = ((rows - 1) * SZ) / 2;
  const { gl } = useThree();
  useEffect(() => { gl.domElement.style.cursor = hover ? "pointer" : ""; }, [hover, gl]);
  return (
    <>
      <Fit halfW={halfW + TW / 2} halfD={halfD + TD / 2} />
      <LabelSync groups={groups} labels={labels} />
      <mesh rotation-x={-Math.PI / 2}>
        <planeGeometry args={[400, 400]} />
        <meshBasicMaterial color={pal.surface} />
      </mesh>
      <Ruling pal={pal} rowsZ={Array.from({ length: rows }, (_, r) => r * SZ - halfD)} step={SZ / 8} />
      {tokens.map((t, i) => (
        <Token
          key={t.id} token={t} state={states[i] ?? "float"} pal={pal} reduced={reduced || !active}
          x={t.col * SX - halfW} z={t.row * SZ - halfD} hovered={hover === t.id}
          register={g => { if (g) groups.set(t.id, g); else groups.delete(t.id); }}
          onHover={on => setHover(h => (on ? t.id : h === t.id ? null : h))}
          onOpen={() => open(t.id)}
        />
      ))}
    </>
  );
}

/** Project each token's top to screen space and move its label there. */
function LabelSync({ groups, labels }: { groups: Reg; labels: Map<string, HTMLSpanElement> }) {
  const v = useMemo(() => new THREE.Vector3(), []);
  useFrame(({ camera, size }) => {
    for (const [id, g] of groups) {
      const el = labels.get(id);
      if (!el) continue;
      g.getWorldPosition(v);
      v.y += TH / 2 + 0.3;
      v.project(camera);
      const x = ((v.x + 1) / 2) * size.width, y = ((1 - v.y) / 2) * size.height;
      el.style.transform = `translate(${x.toFixed(1)}px, ${y.toFixed(1)}px) translate(-50%, -50%)`;
    }
  });
  return null;
}

/** Aim the orthographic camera at the token grid and zoom so the grid and its labels fit the canvas. */
function Fit({ halfW, halfD }: { halfW: number; halfD: number }) {
  const { camera, size, invalidate } = useThree();
  useEffect(() => {
    const cam = camera as THREE.OrthographicCamera;
    cam.up.set(0, 1, 0);
    cam.position.copy(CAM_DIR).multiplyScalar(80);
    cam.lookAt(0, 0, 0);
    cam.updateMatrixWorld();
    const right = new THREE.Vector3().setFromMatrixColumn(cam.matrixWorld, 0);
    const up = new THREE.Vector3().setFromMatrixColumn(cam.matrixWorld, 1);
    let r0 = Infinity, r1 = -Infinity, u0 = Infinity, u1 = -Infinity;
    const p = new THREE.Vector3();
    for (const x of [-halfW, halfW]) for (const z of [-halfD, halfD]) for (const y of [SINK_Y - TH / 2, FLOAT_Y + TH / 2 + 0.7]) {
      p.set(x, y, z);
      const r = p.dot(right), u = p.dot(up);
      r0 = Math.min(r0, r); r1 = Math.max(r1, r); u0 = Math.min(u0, u); u1 = Math.max(u1, u);
    }
    const target = right.clone().multiplyScalar((r0 + r1) / 2).add(up.clone().multiplyScalar((u0 + u1) / 2));
    cam.position.copy(target).addScaledVector(CAM_DIR, 80);
    cam.lookAt(target);
    cam.zoom = Math.min(size.width / ((r1 - r0) * 1.06), size.height / ((u1 - u0) * 1.12));
    cam.updateProjectionMatrix();
    invalidate();
  }, [camera, size.width, size.height, halfW, halfD, invalidate]);
  return null;
}

/** Fine ruled lines across the paper, with a darker line under each row of tokens. */
function Ruling({ pal, rowsZ, step }: { pal: Palette; rowsZ: number[]; step: number }) {
  const [fine, rows] = useMemo(() => {
    const HX = 80, HZ = 40, Y = 0.003;
    const f: number[] = [];
    for (let z = -HZ; z <= HZ; z += step) f.push(-HX, Y, z, HX, Y, z);
    const r: number[] = [];
    for (const z of rowsZ) r.push(-HX, Y * 2, z + TD / 2, HX, Y * 2, z + TD / 2);
    const g1 = new THREE.BufferGeometry(); g1.setAttribute("position", new THREE.Float32BufferAttribute(f, 3));
    const g2 = new THREE.BufferGeometry(); g2.setAttribute("position", new THREE.Float32BufferAttribute(r, 3));
    return [g1, g2];
  }, [rowsZ, step]);
  useEffect(() => () => { fine.dispose(); rows.dispose(); }, [fine, rows]);
  return (
    <>
      <lineSegments geometry={fine}><lineBasicMaterial color={pal.separator} /></lineSegments>
      <lineSegments geometry={rows}><lineBasicMaterial color={pal.ink3} transparent opacity={0.6} /></lineSegments>
    </>
  );
}

interface TokenProps {
  token: FieldToken; state: TokenState; pal: Palette; reduced: boolean; x: number; z: number;
  hovered: boolean; register: (g: THREE.Group | null) => void; onHover: (on: boolean) => void; onOpen: () => void;
}

function Token({ state, pal, reduced, x, z, hovered, register, onHover, onOpen }: TokenProps) {
  const group = useRef<THREE.Group>(null);
  const shadow = useRef<THREE.Mesh>(null);
  const edges = useRef<THREE.LineSegments>(null);
  const restY = state === "moot" ? SINK_Y : FLOAT_Y;
  const startY = useRef(restY).current;
  const { invalidate } = useThree();
  useEffect(() => { register(group.current); return () => register(null); }, [register]);

  useFrame((_, dt) => {
    const g = group.current;
    if (!g) return;
    const far = Math.abs(g.position.y - restY) > 0.002;
    g.position.y = reduced || !far ? restY : THREE.MathUtils.damp(g.position.y, restY, 3.2, Math.min(dt, 0.1));
    if (far && !reduced) invalidate();                     // keep frames coming only while this token moves
    if (shadow.current) {
      const h = Math.max(0, g.position.y - TH / 2);       // height of the token above the paper
      shadow.current.visible = state === "float" && h > 0.02;
      shadow.current.position.y = 0.004 - g.position.y;
    }
  });
  // On a state change ask for a frame; with reduced motion snap straight to the resting height.
  useEffect(() => { if (reduced && group.current) group.current.position.y = restY; invalidate(); }, [reduced, restY, invalidate]);
  useEffect(() => { edges.current?.computeLineDistances(); }, [state]);

  const moot = state === "moot", ghost = state === "ghost";
  const top = moot ? pal.mootTint : pal.surface, side = moot ? pal.mootTint : pal.fill;
  const line = moot ? pal.accent : hovered ? pal.ink : ghost ? pal.ink3 : pal.ink2;
  // Box faces in order +x, -x, +y (top), -y, +z, -z. Ghosts keep invisible faces so they can still be hovered.
  const faces = useMemo(() => [side, side, top, side, side, side].map(c =>
    new THREE.MeshBasicMaterial({ color: c, transparent: ghost, opacity: ghost ? 0 : 1, depthWrite: !ghost })), [top, side, ghost]);
  useEffect(() => () => faces.forEach(m => m.dispose()), [faces]);

  return (
    <group ref={group} position={[x, startY, z]}>
      <mesh
        material={faces}
        onPointerOver={e => { e.stopPropagation(); onHover(true); }}
        onPointerOut={() => onHover(false)}
        onClick={e => { e.stopPropagation(); onOpen(); }}
      >
        <boxGeometry args={[TW, TH, TD]} />
      </mesh>
      <lineSegments ref={edges} geometry={tokenEdges()}>
        {ghost
          ? <lineDashedMaterial key="d" color={line} dashSize={0.09} gapSize={0.07} />
          : <lineBasicMaterial key="b" color={line} />}
      </lineSegments>
      <mesh ref={shadow} rotation-x={-Math.PI / 2} visible={false}>
        <planeGeometry args={[TW * 1.04, TD * 1.04]} />
        <meshBasicMaterial color={pal.fill} />
      </mesh>
    </group>
  );
}
