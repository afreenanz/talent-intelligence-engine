/**
 * Terrain maths shared by the WebGL shader and the page script.
 *
 * The ground is one deterministic function (sums of sines after a small domain warp, no hash
 * and no noise texture). It exists twice, as GLSL and as TypeScript, with the same literal
 * numbers, so anything the script computes about the ground matches what the GPU draws.
 * A unit test checks that both copies use the same constants in the same order.
 */

export const GRID = {
  cols: 340,
  colsNarrow: 170, // below 820px wide
  rows: 224,
  dx: 0.036,
  dz: 0.04,
  zFar: -7.6,
  zNear: 1.36, // zFar + rows * dz
  heightScale: 1.2,
  flySpeed: 0.16, // world units per second
} as const

export const CAMERA = {
  x: 0,
  y: 1.55,
  z: 2.2,
  pitch: 0.5, // radians, looking down
  focal: 2.14,
  drift: 0.22, // max sideways drift with the pointer
} as const

/** Ground height in [0, 1] at ground coordinate (x, y). Keep in sync with HEIGHT_GLSL. */
export function heightAt(px: number, py: number): number {
  const qx = px + 0.35 * Math.sin(0.9 * py + 1.3)
  const qy = py + 0.35 * Math.sin(0.8 * px + 2.1)
  const h =
    0.42 * Math.sin(0.55 * qx + 0.3) * Math.sin(0.47 * qy + 1.7) +
    0.26 * Math.sin(1.13 * qx - 0.71 * qy + 2.2) +
    0.2 * (1 - 2 * Math.abs(Math.sin(0.85 * qx + 1.2 * qy + 0.7))) +
    0.12 * Math.sin(2.17 * qx + 1.63 * qy + 0.5) * Math.sin(1.31 * qy - 0.8) +
    0.07 * Math.sin(4.1 * qx - 3.3 * qy + 1.1) +
    0.04 * Math.sin(7.9 * qx + 6.7 * qy + 3.0)
  return Math.pow(Math.min(1, Math.max(0, 0.5 * h + 0.5)), 1.6)
}

export const HEIGHT_GLSL = /* glsl */ `
float heightAt(vec2 p) {
  vec2 q = p + 0.35 * vec2(sin(0.9 * p.y + 1.3), sin(0.8 * p.x + 2.1));
  float h =
    0.42 * sin(0.55 * q.x + 0.3) * sin(0.47 * q.y + 1.7) +
    0.26 * sin(1.13 * q.x - 0.71 * q.y + 2.2) +
    0.2 * (1.0 - 2.0 * abs(sin(0.85 * q.x + 1.2 * q.y + 0.7))) +
    0.12 * sin(2.17 * q.x + 1.63 * q.y + 0.5) * sin(1.31 * q.y - 0.8) +
    0.07 * sin(4.1 * q.x - 3.3 * q.y + 1.1) +
    0.04 * sin(7.9 * q.x + 6.7 * q.y + 3.0);
  return pow(clamp(0.5 * h + 0.5, 0.0, 1.0), 1.6);
}`

/** World ground point (x, z) to the ground coordinate the shader samples, given the fly offset. */
export function groundCoord(worldX: number, worldZ: number, fly: number): [number, number] {
  // Rows sample the ground at (row - floor(fly/dz)) * dz, and sit at zFar + (row + fract(fly/dz)) * dz.
  // Eliminating `row` gives a continuous mapping: ground_y = worldZ - zFar - fly.
  return [worldX, worldZ - GRID.zFar - fly]
}

/**
 * Cast a ray from the camera through a pointer position (NDC, -1..1) and intersect it with the
 * ground plane y = 0. Uses exactly the camera the vertex shader projects with.
 */
export function pointerToGround(
  ndcX: number,
  ndcY: number,
  aspect: number,
  camX: number,
): [number, number] | null {
  const { y, z, pitch, focal } = CAMERA
  const s = Math.sin(pitch)
  const c = Math.cos(pitch)
  // Camera basis: right = (1,0,0), up = (0, c, -s), forward = (0, -s, -c)
  const vx = (ndcX * aspect) / focal
  const vy = ndcY / focal
  const dirY = vy * c - s
  const dirZ = -vy * s - c
  if (dirY >= -1e-4) return null // ray parallel to or above the horizon
  const t = -y / dirY
  return [camX + vx * t, z + dirZ * t]
}

export interface Ramp {
  name: string
  stops: [number, number, number][]
}

/** One ramp, low to high: deep ink-blue, dusk slate, signal amber, pale amber. No rainbow. */
export const SIGNAL_RAMP: Ramp = {
  name: 'signal',
  stops: [
    [0.09, 0.11, 0.21],
    [0.33, 0.31, 0.4],
    [1.0, 0.54, 0.24],
    [1.0, 0.86, 0.66],
  ],
}

/** Numeric literals in a function body, in order (used by the shader/script parity test). */
export function numericLiterals(source: string): number[] {
  return (source.match(/\d*\.\d+|\b\d+\b/g) ?? []).map(Number)
}
