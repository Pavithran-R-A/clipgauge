# ClipGauge product principles

These principles are project rules for product decisions, interface copy, documentation, and release work. They apply to new screens as well as changes to retained screens.

## 1. Start with the creator's next action

The interface should make the next useful action obvious: add a video, choose a scoring path, review a moment, edit a clip, or export it.

## 2. Explain before asking

Before an action downloads files, sends source-derived material, stores a credential, or changes a session, explain what will happen in plain language.

## 3. Keep local processing local by default

A local provider should keep source media, transcripts, scoring inputs, and rendered output on the user's computer. Cloud use must be an explicit provider choice.

## 4. Make provider choice visible

All supported providers remain reachable in one clear place. Friendly provider names come first; model IDs, endpoints, and authentication details belong behind an Advanced disclosure.

## 5. Separate integrations from scoring

Pexels and Instagram are integrations, not AI providers. Their credentials, network activity, and failure states must be presented separately from scoring providers.

## 6. Treat privacy as a product feature

Privacy is not only a legal note. The app should show what stays local, what may leave the device, and which optional service is responsible.

## 7. Never hide a failure behind a blank state

A missing render, unavailable provider, failed download, or incomplete setup must produce a useful explanation and a next step.

## 8. Do not pretend to know what is unknown

Unknown sizes, unavailable capabilities, incomplete provenance, and unverified connections should be labeled as unknown or unavailable. Never replace them with a reassuring zero or a guessed result.

## 9. Preserve a human explanation for every score

A score should be accompanied by the signals, adjustments, confidence, and limitations that help a creator decide what to do next.

## 10. Put advanced detail behind a deliberate boundary

Technical information matters for debugging and trust, but it should not make the first-run workflow feel like a configuration console. Use a visible disclosure and explain why the detail is useful.

## 11. Design for keyboard and assistive technology users

Every action needs a semantic control, a visible focus state, a meaningful accessible name, and a logical keyboard path. Motion must respect reduced-motion preferences.

## 12. Keep destructive and network actions deliberate

Deleting a session, sending source-derived material, reading browser cookies, or installing components requires clear intent and honest status feedback.

## 13. Preserve provenance and upstream credit

ClipGauge remains an AGPL project derived from [`Blueturboguy07/publikclip`](https://github.com/Blueturboguy07/publikclip). License, attribution, dependency, and asset provenance records are part of the product and must stay accurate.

## 14. Prefer evidence over claims

Release notes, screenshots, benchmarks, accessibility statements, and platform support claims must describe what was actually checked. A limitation is more trustworthy than an unsupported promise.

## Permanent project rules

ClipGauge first-party branding does not use purple, violet, indigo, magenta, yellow, gold, or amber. Legal upstream attribution stays accurate without preserving upstream visual identity. Public UI and documentation use human, concise wording. The public repository root stays clean and does not accumulate internal agent, phase, or closure files. Large downloads are disclosed before they begin and require consent. Technical details belong behind Advanced or Technical details disclosures. Local use remains possible without a mandatory cloud account. Mocked tests are never described as live or model-backed tests. A known project-owned blocker or high-severity defect prevents release.

## How to use these principles

When a proposal conflicts with a principle, document the tradeoff in the issue or pull request. A new screen is not complete until it has an empty state, an error state, a clear escape route, and a test or verification note appropriate to its risk.
