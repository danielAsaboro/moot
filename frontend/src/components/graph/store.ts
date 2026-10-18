// A tiny external store: the scene writes the screen positions of the parts it drew, the HTML callouts read them.
// Keeping it outside React state means a camera move re-renders the callouts only, not the canvas.

export interface Projection {
  w: number; h: number; zoom: number;
  pts: Record<string, [number, number]>;
}

export interface ProjStore {
  get: () => Projection | null;
  set: (p: Projection) => void;
  subscribe: (l: () => void) => () => void;
}

export function createProjStore(): ProjStore {
  let snap: Projection | null = null;
  const ls = new Set<() => void>();
  return {
    get: () => snap,
    set: p => { snap = p; ls.forEach(l => l()); },
    subscribe: l => { ls.add(l); return () => { ls.delete(l); }; },
  };
}

/** Commands the control row sends to the camera. */
export interface ViewApi { reset: () => void; zoomBy: (f: number) => void }
