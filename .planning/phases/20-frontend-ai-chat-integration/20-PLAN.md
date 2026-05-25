# Phase 20 PLAN: Frontend AI Chat Integration (Gemini & ChatGPT Reference)

## Summary
Add UX polish and a safe/usable flow for redirecting users to external AI chat services (ChatGPT, Gemini) with pre-built legal prompts so users can paste and send with minimal effort.

## Goals
- Provide an easy, discoverable workflow to open external chat UIs with a pre-built legal prompt copied to clipboard.
- Surface a legal text preview and citation snippets for users to inspect before redirecting.
- Make UX mobile-friendly and include an in-app modal that explains the flow.

## Non-goals
- Directly sending messages into another origin's chat window (blocked by browser security) unless an official API/session mechanism is used.
- Storing external chat sessions or external-service credentials in this app.

## Tasks
1. UI: Retrievals list & preview (Frontend) — 3d
   - Ensure retrievals returned by `/api/v1/ask` are stored and displayed.
   - Clickable list with preview pane, score, and source metadata.
   - Mobile-friendly layout and truncation rules.

2. UX: Copy & Open flow (Frontend) — 2d
   - `buildExternalPrompt()` produces a compact, Vietnamese-language prompt (system + query + up to 5 snippets).
   - `handleCopyAndOpen()` copies to clipboard and opens external chat in new tab.
   - Visual feedback/tooltip for copy success and instructions.

3. UX: Modal + Help (Frontend) — 1d
   - Modal explaining steps for desktop and mobile.
   - "Don't show again" checkbox stored in localStorage.

4. Accessibility & Internationalization — 1d
   - Ensure buttons have accessible labels and `title` attributes.
   - Vietnamese copy accuracy review.

5. QA & Cross-browser testing — 2d
   - Test clipboard behavior on Chrome, Firefox, Safari (desktop & mobile), and Chromium-based mobile browsers.
   - Test `navigator.clipboard` fallback behavior when not available (show manual copy instructions). 

6. Plan B: Optional server-side integration (design doc) — 2d
   - Document approach for full 1-click send via server-side session creation (OpenAI/Gemini) with acceptance criteria and security considerations.

## Deliverables
- `LegalRAGChat.tsx` updates with retrievals display, preview, copy/open buttons, modal help, and small UX improvements.
- `20-PLAN.md` (this file) recorded in phase folder.
- UAT checklist and short demo recording steps.

## Acceptance Criteria / UAT
- User clicks "Hiển thị Tài liệu" → list of retrievals appears with at least 1 item for a real query.
- User clicks on a retrieval → preview shows the full snippet + source label.
- Clicking "Mở ChatGPT (sao chép prompt)" copies a prompt to clipboard and opens ChatGPT in a new tab. A notice appears explaining user should paste and send.
- The modal help appears on first visit and respects "Không hiển thị lại".
- Clipboard copy works on desktop Chromium; if not supported, the UI shows manual instructions.

## Risks & Mitigations
- Clipboard blocked on some browsers: provide manual copy fallback modal and explicit instructions.
- External UI changes (ChatGPT/Gemini) could break deep-linking; app relies on copy+open approach to be resilient.
- Large prompts may exceed clipboard or external service limits: limit to top 5 snippets and concise system instruction.

## Rollout Plan
- Merge to `develop` or feature branch.
- QA on staging with representative queries.
- Release with small feature flag if desired (ENV var `NEXT_PUBLIC_ENABLE_EXTERNAL_CHAT_BUTTONS`).

## Estimated effort
Total: ~9 person-days (frontend engineer + QA). Smaller incremental MVP can be shipped in ~2-3 days (UI + copy/open + modal).

---
*Created: 2026-05-25*

