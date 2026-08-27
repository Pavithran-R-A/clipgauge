import { getCurrentWindow } from '@tauri-apps/api/window'

export interface DisplayDiagnostics {
  cssViewport: { width: number; height: number }
  devicePixelRatio: number
  screen: { width: number; height: number }
  availableScreen: { width: number; height: number }
  responsiveBreakpoint: 'mobile' | 'stacked' | 'wide'
  innerPhysical: { width: number; height: number } | null
  outerPhysical: { width: number; height: number } | null
  scaleFactor: number | null
}

export function logicalViewportSnapshot(input: {
  cssWidth: number
  cssHeight: number
  devicePixelRatio: number
  screenWidth?: number
  screenHeight?: number
  availableScreenWidth?: number
  availableScreenHeight?: number
  innerPhysical?: { width: number; height: number } | null
  outerPhysical?: { width: number; height: number } | null
  scaleFactor?: number | null
}): DisplayDiagnostics {
  const width = Math.round(input.cssWidth)
  return {
    cssViewport: { width, height: Math.round(input.cssHeight) },
    devicePixelRatio: Number(input.devicePixelRatio) || 1,
    screen: { width: Math.round(input.screenWidth ?? width), height: Math.round(input.screenHeight ?? input.cssHeight) },
    availableScreen: { width: Math.round(input.availableScreenWidth ?? input.screenWidth ?? width), height: Math.round(input.availableScreenHeight ?? input.screenHeight ?? input.cssHeight) },
    responsiveBreakpoint: width <= 760 ? 'mobile' : width <= 1050 ? 'stacked' : 'wide',
    innerPhysical: input.innerPhysical ?? null,
    outerPhysical: input.outerPhysical ?? null,
    scaleFactor: input.scaleFactor ?? null
  }
}

export async function readDisplayDiagnostics(): Promise<DisplayDiagnostics> {
  const current = getCurrentWindow()
  const [innerPhysical, outerPhysical, scaleFactor] = await Promise.all([
    current.innerSize().catch(() => null),
    current.outerSize().catch(() => null),
    current.scaleFactor().catch(() => null)
  ])
  return logicalViewportSnapshot({
    cssWidth: window.innerWidth,
    cssHeight: window.innerHeight,
    devicePixelRatio: window.devicePixelRatio,
    screenWidth: window.screen.width,
    screenHeight: window.screen.height,
    availableScreenWidth: window.screen.availWidth,
    availableScreenHeight: window.screen.availHeight,
    innerPhysical: innerPhysical ? { width: innerPhysical.width, height: innerPhysical.height } : null,
    outerPhysical: outerPhysical ? { width: outerPhysical.width, height: outerPhysical.height } : null,
    scaleFactor
  })
}
