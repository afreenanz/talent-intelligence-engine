/**
 * The landing hero: ~76k points laid on the ground as a regular grid, seen in perspective, so they
 * read as a glowing terrain flying slowly toward the viewer. Raw WebGL points only: no lines,
 * triangles, textures or libraries.
 *
 * Height comes from `heightAt` (see lib/terrain.ts), identical in GLSL and TS. Points are coloured
 * by height on one ramp; points on contour lines burn brighter; a scanner band sweeps to the
 * horizon; the ground swells under the pointer and a click sends a ring outward.
 */
import { useEffect, useRef } from 'react'

import { CAMERA, GRID, HEIGHT_GLSL, SIGNAL_RAMP, pointerToGround } from '@/lib/terrain'

const VERT = /* glsl */ `
precision highp float;
attribute vec2 aCell;            // (column, row): the only vertex attribute
uniform float uCols, uFly, uTime, uGrow, uAspect, uDpr, uCamX, uScan;
uniform vec2 uHover;             // eased ground hit point (world x, z)
uniform float uHoverOn;
uniform vec3 uRing;              // (world x, world z, age); age < 0 means no ring
varying vec3 vColor;
varying float vAlpha;
${HEIGHT_GLSL}

vec3 ramp(float t) {
  vec3 c0 = vec3(${SIGNAL_RAMP.stops[0].join(', ')});
  vec3 c1 = vec3(${SIGNAL_RAMP.stops[1].join(', ')});
  vec3 c2 = vec3(${SIGNAL_RAMP.stops[2].join(', ')});
  vec3 c3 = vec3(${SIGNAL_RAMP.stops[3].join(', ')});
  if (t < 0.4) return mix(c0, c1, t / 0.4);
  if (t < 0.75) return mix(c1, c2, (t - 0.4) / 0.35);
  return mix(c2, c3, (t - 0.75) / 0.25);
}

void main() {
  float dz = ${GRID.dz};
  float x = (aCell.x - (uCols - 1.0) * 0.5) * ${GRID.dx};
  float z = ${GRID.zFar} + (aCell.y + fract(uFly / dz)) * dz;
  vec2 g = vec2(x, (aCell.y - floor(uFly / dz)) * dz);
  float h = heightAt(g);

  // Load: terrain grows out of the flat, near edge first.
  float nearness = (${GRID.zNear} - z) / (${GRID.zNear} - (${GRID.zFar}));
  float grow = smoothstep(0.0, 1.0, (uGrow - nearness * 0.7) / 0.3);

  float hover = uHoverOn * exp(-2.6 * dot(vec2(x, z) - uHover, vec2(x, z) - uHover));
  float ring = 0.0;
  if (uRing.z >= 0.0) {
    float front = length(vec2(x, z) - uRing.xy) - 2.4 * uRing.z;
    ring = exp(-5.0 * front * front) * exp(-1.1 * uRing.z);
  }
  float y = h * ${GRID.heightScale} * grow + 0.4 * hover + 0.25 * ring;

  // Hand-rolled perspective camera (must match pointerToGround in lib/terrain.ts).
  vec3 rel = vec3(x - uCamX, y - ${CAMERA.y}, z - ${CAMERA.z});
  float s = sin(${CAMERA.pitch}); float c = cos(${CAMERA.pitch});
  float depth = -rel.y * s - rel.z * c;
  float up = rel.y * c - rel.z * s;
  if (depth < 0.05) { gl_Position = vec4(2.0, 2.0, 2.0, 1.0); return; }
  gl_Position = vec4(${CAMERA.focal} * rel.x / depth / uAspect, ${CAMERA.focal} * up / depth, 0.0, 1.0);

  float contour = smoothstep(0.16, 0.02, abs(fract(11.0 * h) - 0.5));
  float scan = exp(-pow(z - uScan, 2.0) / 0.02);
  gl_PointSize = (1.35 + 5.6 / depth) * uDpr * (1.0 + 0.7 * contour + 1.1 * scan + 0.8 * hover + 1.4 * ring);

  vec3 col = ramp(h) * (1.0 + 1.3 * contour);
  col = mix(col, vec3(1.0, 0.96, 0.9), clamp(0.55 * scan + 0.5 * hover + 0.8 * ring, 0.0, 1.0));
  vColor = col;
  float horizonFade = smoothstep(${GRID.zFar}, ${GRID.zFar} + 2.5, z);
  vAlpha = min(1.0, 3.4 / pow(depth, 1.3)) * horizonFade * (0.35 + 0.65 * grow);
}`

const FRAG = /* glsl */ `
precision mediump float;
varying vec3 vColor;
varying float vAlpha;
void main() {
  float d = length(gl_PointCoord - 0.5);
  float a = smoothstep(0.5, 0.15, d) * vAlpha;   // soft round point
  gl_FragColor = vec4(vColor * a, a);              // additive blending
}`

function compile(gl: WebGLRenderingContext, type: number, src: string): WebGLShader {
  const sh = gl.createShader(type)!
  gl.shaderSource(sh, src)
  gl.compileShader(sh)
  if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
    throw new Error(gl.getShaderInfoLog(sh) ?? 'shader compile failed')
  }
  return sh
}

interface Props {
  onPointsInView?: (n: number) => void
}

export function TerrainField({ onPointsInView }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const markerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current!
    const gl = canvas.getContext('webgl', { antialias: false, premultipliedAlpha: true, alpha: true })
    if (!gl) return // no WebGL: the CSS background behind the canvas is the fallback
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches

    let prog: WebGLProgram
    try {
      prog = gl.createProgram()!
      const vs = compile(gl, gl.VERTEX_SHADER, VERT)
      const fs = compile(gl, gl.FRAGMENT_SHADER, FRAG)
      gl.attachShader(prog, vs)
      gl.attachShader(prog, fs)
      gl.linkProgram(prog)
      gl.deleteShader(vs) // flagged; freed with the program
      gl.deleteShader(fs)
      if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(prog) ?? '')
    } catch (err) {
      console.warn('Terrain shader unavailable; showing static background.', err)
      return
    }
    gl.useProgram(prog)
    const u = (n: string) => gl.getUniformLocation(prog, n)
    const loc = {
      cols: u('uCols'), fly: u('uFly'), time: u('uTime'), grow: u('uGrow'), aspect: u('uAspect'),
      dpr: u('uDpr'), camX: u('uCamX'), scan: u('uScan'), hover: u('uHover'), hoverOn: u('uHoverOn'),
      ring: u('uRing'),
    }

    let cols = 0
    let count = 0
    const buffer = gl.createBuffer()
    const attr = gl.getAttribLocation(prog, 'aCell')
    const buildGrid = (width: number) => {
      const c = width < 820 ? GRID.colsNarrow : GRID.cols
      if (c === cols) return
      cols = c
      const data = new Float32Array(cols * GRID.rows * 2)
      let i = 0
      for (let r = 0; r < GRID.rows; r++) for (let k = 0; k < cols; k++) { data[i++] = k; data[i++] = r }
      gl.bindBuffer(gl.ARRAY_BUFFER, buffer)
      gl.bufferData(gl.ARRAY_BUFFER, data, gl.STATIC_DRAW)
      gl.enableVertexAttribArray(attr)
      gl.vertexAttribPointer(attr, 2, gl.FLOAT, false, 0, 0)
      count = cols * GRID.rows
      onPointsInView?.(count)
    }

    gl.enable(gl.BLEND)
    gl.blendFunc(gl.ONE, gl.ONE) // additive (colour is premultiplied in the fragment shader)
    gl.clearColor(0, 0, 0, 0)

    let dpr = Math.min(window.devicePixelRatio || 1, 2)
    const resize = () => {
      const { clientWidth: w, clientHeight: h } = canvas
      dpr = Math.min(window.devicePixelRatio || 1, 2)
      canvas.width = Math.round(w * dpr)
      canvas.height = Math.round(h * dpr)
      gl.viewport(0, 0, canvas.width, canvas.height)
      buildGrid(w)
      dirty = true
    }

    // ---- interaction state
    let pointer: { x: number; y: number } | null = null
    let lastPointerAt = 0
    const hover = { x: 0, z: -1, on: 0 }
    let ring: { x: number; z: number; t0: number } | null = null
    let camX = 0
    let dirty = true

    const toNdc = (e: PointerEvent) => {
      const rect = canvas.getBoundingClientRect()
      return { x: ((e.clientX - rect.left) / rect.width) * 2 - 1, y: 1 - ((e.clientY - rect.top) / rect.height) * 2,
        px: e.clientX - rect.left, py: e.clientY - rect.top }
    }
    const onMove = (e: PointerEvent) => {
      const p = toNdc(e)
      pointer = { x: p.x, y: p.y }
      lastPointerAt = performance.now()
      if (markerRef.current) {
        markerRef.current.style.transform = `translate(${p.px}px, ${p.py}px)`
        markerRef.current.style.opacity = '1'
      }
      dirty = true
    }
    const onLeave = () => {
      pointer = null
      if (markerRef.current) markerRef.current.style.opacity = '0'
    }
    const onClick = (e: PointerEvent) => {
      const p = toNdc(e)
      const hit = pointerToGround(p.x, p.y, canvas.clientWidth / canvas.clientHeight, camX)
      if (hit) ring = { x: hit[0], z: hit[1], t0: performance.now() }
      dirty = true
    }
    canvas.addEventListener('pointermove', onMove)
    canvas.addEventListener('pointerleave', onLeave)
    canvas.addEventListener('pointerdown', onClick)

    const ro = new ResizeObserver(resize)
    ro.observe(canvas)
    resize()

    // ---- loop
    const start = performance.now()
    let last = start
    let fly = 0
    let raf = 0
    let running = !document.hidden

    const frame = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000)
      last = now
      const t = (now - start) / 1000
      const aspect = canvas.clientWidth / Math.max(1, canvas.clientHeight)

      // After 3 idle seconds an invisible hand flies a slow survey pattern (not under reduced motion).
      let target = pointer
      if (!target && !reduced && now - lastPointerAt > 3000) {
        target = { x: 0.55 * Math.sin(t * 0.21), y: -0.35 + 0.25 * Math.sin(t * 0.13 + 1.1) }
      }
      if (!reduced) fly += GRID.flySpeed * dt
      const hit = target ? pointerToGround(target.x, target.y, aspect, camX) : null
      const k = 1 - Math.exp(-9 * dt) // ease at 9/s
      if (hit) {
        hover.x += (hit[0] - hover.x) * k
        hover.z += (hit[1] - hover.z) * k
      }
      const goalOn = hit ? 1 : 0
      hover.on += (goalOn - hover.on) * k
      camX += ((pointer ? pointer.x : 0) * CAMERA.drift - camX) * (1 - Math.exp(-2 * dt))
      const ringAge = ring ? (now - ring.t0) / 1000 : -1
      if (ring && ringAge > 4) ring = null

      gl.clear(gl.COLOR_BUFFER_BIT)
      gl.uniform1f(loc.cols, cols)
      gl.uniform1f(loc.fly, fly)
      gl.uniform1f(loc.time, t)
      gl.uniform1f(loc.grow, reduced ? 1 : Math.min(1.4, t / 2.4 * 1.4))
      gl.uniform1f(loc.aspect, aspect)
      gl.uniform1f(loc.dpr, dpr)
      gl.uniform1f(loc.camX, camX)
      gl.uniform1f(loc.scan, reduced ? -100 : GRID.zNear - ((t % 7) / 7) * (GRID.zNear - GRID.zFar))
      gl.uniform2f(loc.hover, hover.x, hover.z)
      gl.uniform1f(loc.hoverOn, hover.on)
      gl.uniform3f(loc.ring, ring?.x ?? 0, ring?.z ?? 0, ring ? ringAge : -1)
      gl.drawArrays(gl.POINTS, 0, count)
      dirty = false

      // Reduced motion: redraw only while something is actually changing.
      const settling = Math.abs(goalOn - hover.on) > 0.01 || ring !== null || (hit && Math.abs(hit[0] - hover.x) > 0.002)
      const keepGoing = !reduced || settling || dirty
      if (running && keepGoing) raf = requestAnimationFrame(frame)
      else raf = 0
    }
    const kick = () => {
      if (running && !raf) {
        last = performance.now()
        raf = requestAnimationFrame(frame)
      }
    }
    const kickOnInput = () => kick()
    canvas.addEventListener('pointermove', kickOnInput)
    canvas.addEventListener('pointerdown', kickOnInput)
    const onVisibility = () => {
      running = !document.hidden // pause when the tab is hidden
      if (running) kick()
      else if (raf) { cancelAnimationFrame(raf); raf = 0 }
    }
    document.addEventListener('visibilitychange', onVisibility)
    kick()

    return () => {
      cancelAnimationFrame(raf)
      ro.disconnect()
      document.removeEventListener('visibilitychange', onVisibility)
      canvas.removeEventListener('pointermove', onMove)
      canvas.removeEventListener('pointerleave', onLeave)
      canvas.removeEventListener('pointerdown', onClick)
      canvas.removeEventListener('pointermove', kickOnInput)
      canvas.removeEventListener('pointerdown', kickOnInput)
      // Free our resources but keep the context: getContext() on the same canvas returns the SAME
      // context on remount (StrictMode, route changes), and a lost one can't compile shaders.
      gl.deleteBuffer(buffer)
      gl.deleteProgram(prog)
    }
  }, [onPointsInView])

  return (
    <>
      <canvas ref={canvasRef} aria-hidden="true" className="absolute inset-0 h-full w-full cursor-crosshair" />
      <div
        ref={markerRef}
        aria-hidden="true"
        className="pointer-events-none absolute left-0 top-0 -ml-3 -mt-3 size-6 rounded-full border border-signal-soft/70 opacity-0 transition-opacity duration-300"
      />
    </>
  )
}
