import { CAMERA, GRID, HEIGHT_GLSL, groundCoord, heightAt, numericLiterals, pointerToGround } from './terrain'

describe('terrain height function', () => {
  it('stays in [0, 1] and is deterministic', () => {
    for (let i = 0; i < 2000; i++) {
      const x = (i % 50) * 0.37 - 9
      const y = Math.floor(i / 50) * 0.41 - 8
      const h = heightAt(x, y)
      expect(h).toBeGreaterThanOrEqual(0)
      expect(h).toBeLessThanOrEqual(1)
      expect(heightAt(x, y)).toBe(h)
    }
  })

  it('uses exactly the same set of constants as the GLSL copy', () => {
    const js = heightAt.toString()
    const body = (s: string) => s.slice(s.indexOf('{'))
    // The transpiled TS drops leading zeros (.35) and writes the warp constant twice where the
    // GLSL uses one vec2, so compare the sets of distinct constants rather than the raw text.
    const distinct = (src: string) => [...new Set(numericLiterals(body(src)))].sort((a, b) => a - b)
    expect(distinct(HEIGHT_GLSL)).toEqual(distinct(js))
    expect(distinct(js)).toHaveLength(distinct(HEIGHT_GLSL).length)
  })
})

describe('pointer to ground', () => {
  it('maps the screen centre to a point straight ahead of the camera', () => {
    const hit = pointerToGround(0, 0, 16 / 9, 0)
    expect(hit).not.toBeNull()
    const [x, z] = hit!
    expect(x).toBeCloseTo(0)
    // Looking down 0.5 rad from height 1.55: ground hit at z = 2.2 - 1.55 / tan(0.5)
    expect(z).toBeCloseTo(CAMERA.z - CAMERA.y / Math.tan(CAMERA.pitch), 5)
  })

  it('returns null above the horizon', () => {
    // Horizon sits at ndcY = focal * tan(pitch) = 1.17, just above the top edge of the frame.
    const horizon = CAMERA.focal * Math.tan(CAMERA.pitch)
    expect(pointerToGround(0, horizon + 0.05, 1, 0)).toBeNull()
    expect(pointerToGround(0, horizon - 0.05, 1, 0)).not.toBeNull()
  })

  it('is continuous across the row wrap of the flying grid', () => {
    const a = groundCoord(0.5, -3, 0.0399)
    const b = groundCoord(0.5, -3, 0.0401)
    expect(Math.abs(a[1] - b[1])).toBeLessThan(0.001)
    expect(GRID.zNear).toBeCloseTo(GRID.zFar + GRID.rows * GRID.dz)
  })
})
