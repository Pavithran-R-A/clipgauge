import test from 'node:test'
import assert from 'node:assert/strict'
import { physicalCandidates, REQUIRED_EMULATED_SCALE_FACTORS, validateDisplayFacts, validateEmulatedDisplayFacts } from './windows-ui-dpi-contract.mjs'

test('derives only floor and ceil physical sizes', () => {
  assert.deepEqual(physicalCandidates(1366, 1.25), [1707, 1708])
  assert.deepEqual(physicalCandidates(1920, 1.5), [2880])
})

test('accepts a measured logical and physical client match', () => {
  const result = validateDisplayFacts({
    requested_logical_size: { width: 1366, height: 768 },
    css_viewport: { width: 1366, height: 768 },
    document_client: { width: 1366, height: 768 },
    actual_native_inner_size: { width: 1708, height: 960 },
    native_client_rect: { width: 1708, height: 960 },
    client_capture: { width: 1708, height: 960 },
    tauri_scale_factor: 1.25,
    dpi_for_window: 120,
  })
  assert.equal(result.pass, true)
  assert.deepEqual(result.physical_candidates, { width: [1707, 1708], height: [960] })
})

test('allows document client width lost to a scrollbar', () => {
  const result = validateDisplayFacts({
    requested_logical_size: { width: 1366, height: 768 },
    css_viewport: { width: 1366, height: 768 },
    document_client: { width: 1351, height: 768 },
    actual_native_inner_size: { width: 1708, height: 960 },
    native_client_rect: { width: 1708, height: 960 },
    client_capture: { width: 1708, height: 960 },
    tauri_scale_factor: 1.25,
    dpi_for_window: 120,
  })
  assert.equal(result.pass, true)
})

test('rejects a bitmap-sized value used as client geometry', () => {
  const result = validateDisplayFacts({
    requested_logical_size: { width: 1366, height: 768 },
    css_viewport: { width: 1366, height: 768 },
    document_client: { width: 1366, height: 768 },
    actual_native_inner_size: { width: 1708, height: 960 },
    native_client_rect: { width: 1708, height: 960 },
    client_capture: { width: 1367, height: 768 },
    tauri_scale_factor: 1.25,
    dpi_for_window: 120,
  })
  assert.equal(result.pass, false)
  assert.match(result.errors.join('; '), /client capture dimensions mismatch/)
})

test('rejects logical viewport drift', () => {
  const result = validateDisplayFacts({
    requested_logical_size: { width: 1440, height: 900 },
    css_viewport: { width: 1439, height: 900 },
    document_client: { width: 1439, height: 900 },
    actual_native_inner_size: { width: 1439, height: 900 },
    native_client_rect: { width: 1439, height: 900 },
    client_capture: { width: 1439, height: 900 },
    tauri_scale_factor: 1,
    dpi_for_window: 96,
  })
  assert.equal(result.pass, false)
  assert.match(result.errors.join('; '), /logical browser viewport mismatch/)
})

test('accepts required controlled emulation scales', () => {
  assert.deepEqual(REQUIRED_EMULATED_SCALE_FACTORS, [1, 1.25, 1.5, 1.75, 2])
  for (const scale of REQUIRED_EMULATED_SCALE_FACTORS) {
    assert.equal(validateEmulatedDisplayFacts({
      emulated_scale_factor: scale,
      device_pixel_ratio: scale,
      css_viewport: { width: 1200, height: 800 },
      document_client: { width: 1200, height: 800 },
    }).pass, true)
  }
})

test('accepts DevTools floating point DPR noise', () => {
  const result = validateEmulatedDisplayFacts({
    emulated_scale_factor: 1.5,
    device_pixel_ratio: 1.5000000596046448,
    css_viewport: { width: 1200, height: 800 },
    document_client: { width: 1200, height: 800 },
  })
  assert.equal(result.pass, true)
})
