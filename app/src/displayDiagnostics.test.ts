import { describe, expect, it } from 'vitest'
import { logicalViewportSnapshot } from './displayDiagnostics'

describe('logical display diagnostics', () => {
  it('keeps CSS viewport and physical window facts separate', () => {
    expect(logicalViewportSnapshot({ cssWidth: 1279.6, cssHeight: 799.4, devicePixelRatio: 1.25, screenWidth: 1920, screenHeight: 1200, availableScreenWidth: 1920, availableScreenHeight: 1160, innerPhysical: { width: 1600, height: 1000 }, outerPhysical: { width: 1620, height: 1040 }, scaleFactor: 1.25 })).toEqual({
      cssViewport: { width: 1280, height: 799 },
      devicePixelRatio: 1.25,
      screen: { width: 1920, height: 1200 },
      availableScreen: { width: 1920, height: 1160 },
      responsiveBreakpoint: 'wide',
      innerPhysical: { width: 1600, height: 1000 },
      outerPhysical: { width: 1620, height: 1040 },
      scaleFactor: 1.25
    })
  })
})
