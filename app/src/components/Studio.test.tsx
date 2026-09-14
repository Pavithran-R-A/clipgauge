import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { open } from '@tauri-apps/plugin-dialog'
import Studio from './Studio'

vi.mock('@tauri-apps/plugin-dialog', () => ({ open: vi.fn() }))

describe('Studio output controls', () => {
  it('disables cloud scoring until a cloud provider is configured', () => {
    render(
      <Studio
        jobs={[]}
        running={false}
        runState="IDLE"
        cancelling={false}
        startedAt={null}
        stages={{}}
        error={null}
        errorCode={null}
        notice={null}
        cloudConfigured={false}
        onRun={vi.fn()}
        onCancel={vi.fn()}
        onContinueCpu={vi.fn()}
        onNavigate={vi.fn()}
        selectedProvider="clipgauge-local"
        onSelectProvider={vi.fn()}
        onOpenJob={vi.fn()}
        onResume={vi.fn()}
      />
    )

    expect(screen.getByRole('button', { name: /Balanced \/ Hybrid/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: /Best Quality/i })).toBeDisabled()
    expect(screen.getByText('Configure a cloud provider and model in AI Providers before choosing Hybrid or Best Quality.')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('ClipGauge Local')
  })

  it('shows the selected cloud provider and model before creation', async () => {
    render(
      <Studio
        jobs={[]}
        running={false}
        runState="IDLE"
        cancelling={false}
        startedAt={null}
        stages={{}}
        error={null}
        errorCode={null}
        notice={null}
        cloudConfigured
        onRun={vi.fn()}
        onCancel={vi.fn()}
        onContinueCpu={vi.fn()}
        onNavigate={vi.fn()}
        selectedProvider="openrouter"
        onSelectProvider={vi.fn()}
        onOpenJob={vi.fn()}
        onResume={vi.fn()}
      />
    )

    await userEvent.click(screen.getByRole('button', { name: /Balanced \/ Hybrid/i }))

    expect(screen.getAllByText(/OpenRouter Free - openrouter\/free/)).toHaveLength(2)
  })

  it.each([
    ['clipgauge-local', 'private', 'clipgauge-local/qwen3-4b-q4_k_m'],
    ['ollama', 'private', 'llama3.2:3b'],
    ['lmstudio', 'private', 'qwen2.5-7b-instruct'],
    ['groq', 'balanced', 'openai/gpt-oss-20b'],
    ['groq', 'best', 'openai/gpt-oss-20b'],
    ['openrouter', 'balanced', 'openrouter/free'],
    ['custom', 'best', 'my-model'],
  ] as const)('passes the selected provider and model for %s + %s', async (provider, mode, model) => {
    const onRun = vi.fn()
    render(
      <Studio
        jobs={[]}
        running={false}
        runState="IDLE"
        cancelling={false}
        startedAt={null}
        stages={{}}
        error={null}
        errorCode={null}
        notice={null}
        cloudConfigured
        providerEndpoint={provider === 'custom' ? 'https://custom.example/v1' : undefined}
        localModelId={provider === 'clipgauge-local' ? model : undefined}
        providerModel={model}
        onRun={onRun}
        onCancel={vi.fn()}
        onContinueCpu={vi.fn()}
        onNavigate={vi.fn()}
        selectedProvider={provider}
        onSelectProvider={vi.fn()}
        onOpenJob={vi.fn()}
        onResume={vi.fn()}
      />,
    )

    await userEvent.type(screen.getByLabelText('Video link'), 'https://example.com/video')
    if (mode !== 'private') await userEvent.click(screen.getByRole('button', { name: new RegExp(mode === 'balanced' ? 'Balanced / Hybrid' : 'Best Quality') }))
    await userEvent.click(screen.getByRole('button', { name: 'Create clips' }))

    expect(onRun).toHaveBeenCalledTimes(1)
    expect(onRun.mock.calls[0]?.slice(0, 5)).toEqual(['https://example.com/video', provider, 'classic', model, undefined])
    expect(onRun.mock.calls[0]?.[8]).toBe(mode)
  })

  it('describes private scoring using the selected local provider', () => {
    render(
      <Studio
        jobs={[]}
        running={false}
        runState="IDLE"
        cancelling={false}
        startedAt={null}
        stages={{}}
        error={null}
        errorCode={null}
        notice={null}
        providerModel="llama3.2:3b"
        selectedProvider="ollama"
        onRun={vi.fn()}
        onCancel={vi.fn()}
        onContinueCpu={vi.fn()}
        onNavigate={vi.fn()}
        onSelectProvider={vi.fn()}
        onOpenJob={vi.fn()}
        onResume={vi.fn()}
      />,
    )

    expect(screen.getByText('Use your selected local provider. No cloud.')).toBeInTheDocument()
  })

  it('blocks a cloud provider from private mode', async () => {
    const onRun = vi.fn()
    render(
      <Studio
        jobs={[]}
        running={false}
        runState="IDLE"
        cancelling={false}
        startedAt={null}
        stages={{}}
        error={null}
        errorCode={null}
        notice={null}
        cloudConfigured
        onRun={onRun}
        onCancel={vi.fn()}
        onContinueCpu={vi.fn()}
        onNavigate={vi.fn()}
        selectedProvider="groq"
        onSelectProvider={vi.fn()}
        onOpenJob={vi.fn()}
        onResume={vi.fn()}
      />,
    )

    await userEvent.type(screen.getByLabelText('Video link'), 'https://example.com/video')

    expect(screen.getByRole('button', { name: 'Create clips' })).toBeDisabled()
    expect(screen.getByRole('alert')).toHaveTextContent('Private mode requires a local provider')
    expect(onRun).not.toHaveBeenCalled()
  })

  it.each(['SUCCEEDED', 'FAILED', 'CANCELLED'] as const)('keeps final elapsed time for %s runs', (runState) => {
    render(
      <Studio
        jobs={[]}
        running={false}
        runState={runState}
        cancelling={false}
        startedAt={null}
        elapsedSeconds={83}
        stages={{}}
        error={null}
        errorCode={null}
        notice={null}
        onRun={vi.fn()}
        onCancel={vi.fn()}
        onContinueCpu={vi.fn()}
        onNavigate={vi.fn()}
        selectedProvider="clipgauge-local"
        onSelectProvider={vi.fn()}
        onOpenJob={vi.fn()}
        onResume={vi.fn()}
      />
    )

    expect(screen.getByText('1:23 elapsed')).toBeInTheDocument()
  })

  it('discloses the cloud-scoring data boundary before a run', async () => {
    render(
      <Studio
        jobs={[]}
        running={false}
        runState="IDLE"
        cancelling={false}
        startedAt={null}
        stages={{}}
        error={null}
        errorCode={null}
        notice={null}
        onRun={vi.fn()}
        onCancel={vi.fn()}
        onContinueCpu={vi.fn()}
        onNavigate={vi.fn()}
        selectedProvider="openrouter"
        onSelectProvider={vi.fn()}
        onOpenJob={vi.fn()}
        onResume={vi.fn()}
      />
    )

    await userEvent.click(screen.getByRole('button', { name: /Balanced \/ Hybrid/i }))

    expect(screen.getByRole('note')).toHaveTextContent('What leaves this computer: candidate transcript, candidate metadata, and sampled images when visual scoring is supported.')
    expect(screen.getByRole('note')).toHaveTextContent('The full source file stays on this computer.')
  })

  it('lets creators choose the review breadth', async () => {
    render(
      <Studio
        jobs={[]}
        running={false}
        runState="IDLE"
        cancelling={false}
        startedAt={null}
        stages={{}}
        error={null}
        errorCode={null}
        notice={null}
        onRun={vi.fn()}
        onCancel={vi.fn()}
        onContinueCpu={vi.fn()}
        onNavigate={vi.fn()}
        selectedProvider="clipgauge-local"
        onSelectProvider={vi.fn()}
        onOpenJob={vi.fn()}
        onResume={vi.fn()}
      />
    )

    const more = screen.getByRole('button', { name: /More options/i })
    expect(more).toHaveAttribute('aria-pressed', 'false')
    await userEvent.click(more)
    expect(more).toHaveAttribute('aria-pressed', 'true')
  })

  it('surfaces video-picker failures without an unhandled rejection', async () => {
    vi.mocked(open).mockRejectedValueOnce(new Error('dialog unavailable'))
    render(
      <Studio
        jobs={[]}
        running={false}
        runState="IDLE"
        cancelling={false}
        startedAt={null}
        stages={{}}
        error={null}
        errorCode={null}
        notice={null}
        onRun={vi.fn()}
        onCancel={vi.fn()}
        onContinueCpu={vi.fn()}
        onNavigate={vi.fn()}
        selectedProvider="clipgauge-local"
        onSelectProvider={vi.fn()}
        onOpenJob={vi.fn()}
        onResume={vi.fn()}
      />
    )

    await userEvent.click(screen.getByRole('button', { name: 'Choose video' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('The video picker could not open. Retry the action.')
  })
})
