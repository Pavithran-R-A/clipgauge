# v0.5.2 Windows Evidence Architecture

The Windows qualification produces two different kinds of evidence for the credential-removal confirmation state. They must not be conflated.

## Owner-window evidence

For each requested viewport, `1366x768` and `1920x1080`, the harness sizes the ClipGauge owner window with the existing bounded `Size-Window` calibration. Immediately before invoking the semantic Remove control, it captures the owner window with the normal single-window WinAppCLI capture path while no native modal is open. The resulting `credential-removal-confirmation-<viewport>.png` is an application-window screenshot and **must be exactly the requested viewport dimensions**.

The owner screenshot is not resized, stretched, cropped, or otherwise cosmetically altered. Its dimensions are validated from the produced PNG.

## Native-dialog evidence

For the credential-removal acceptance state, the harness explicitly selects **OpenRouter Free** and verifies its detail view and saved-credential Remove action before capturing the owner state. After the real Remove action, it waits for a genuine native confirmation window. Acceptance requires all of the following observed facts: the window belongs to the ClipGauge process; its class is `#32770`; its title is `ClipGauge`; the WinAppCLI UI Automation tree is inspectable; the expected confirmation message and OK and Cancel controls are exposed; and the dialog is accepted through its real semantic control or the bounded keyboard fallback only when UIA does not expose an invokable button.

The harness reads the dialog’s `ContentText` through WinAppCLI’s machine-readable `get-value ContentText -w <dialog HWND> --json` path and parses the non-empty JSON `text` field. Full-message semantics are never checked against elided human-readable `inspect` or `search` prose. The value must include both `OpenRouter Free` and `does not revoke the provider key`.

The harness captures the native dialog HWND itself as `credential-removal-confirmation-dialog-<viewport>.png`. This is a truthful native-dialog image and **is not required to equal** `1366x768` or `1920x1080`. Its actual dimensions, hash, HWND, owning PID, class, title, machine-readable ContentText method/result, UIA result, and post-removal result are recorded in `credential-removal-confirmation-<viewport>.json`.

The native-dialog PNG must exist, have positive reasonable dimensions, be nonblank/nonuniform, and have a hash different from the owner-window PNG. The metadata must include the explicit provider, requested owner viewport, exact owner dimensions/hash, truthful native-dialog dimensions/hash, dialog HWND/PID/class/title, machine-readable ContentText proof method and booleans, OK/Cancel observations, and semantic removal results. The confirmation dialog must close after genuine acceptance, and OpenRouter Free must transition to `Not configured` before the state is marked passed.

## Evidence integrity

The sentinel and credentials must not appear in logs, metadata, screenshots, or other artifacts. The evidence validator must fail on sentinel leakage, missing artifacts, incorrect owner dimensions, implausible or uniform dialog images, identical owner/dialog hashes, missing ownership/UIA metadata, or an absent post-removal transition. No synthetic modal, fake DOM dialog, screenshot transformation, or hidden production control may be used to satisfy this gate.
