export function getTauriBridgeFacts(windowObject = globalThis) {
  const tauri = windowObject?.__TAURI__
  const internals = windowObject?.__TAURI_INTERNALS__
  return {
    tauri_global: Boolean(tauri),
    tauri_core: Boolean(tauri?.core),
    tauri_core_invoke: typeof tauri?.core?.invoke === 'function',
    internals_global: Boolean(internals),
    internals_invoke: typeof internals?.invoke === 'function',
  }
}

export function hasTauriInvoke(facts) {
  return facts.tauri_core_invoke || facts.internals_invoke
}
