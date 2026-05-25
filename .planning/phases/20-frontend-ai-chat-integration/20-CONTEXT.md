# Phase 20: Frontend AI Chat Integration

## Objective
Extend the frontend to support quick reference to external AI chat services (Gemini, ChatGPT) with pre-loaded legal context from the current search query and retrieved documents.

## Background

Previous frontend phases completed:
- Phase 13: Original Content Display with Highlights
- Phase 14: Chat History & RAG Context Loop  
- Phase 15: Legal Domain UI Tags & Reranking

Current state shows users can search legal documents and get AI-generated responses with citations. This phase adds a convenience feature: buttons to continue conversations in external AI services (Gemini, ChatGPT) without manually copying context.

## Scope

### In Scope
- Add "Chat with Gemini" and "Chat with ChatGPT" buttons to the search results/response view
- Pre-populate external AI chat with:
  - Original user query
  - Retrieved legal document citations and snippets
  - System prompt defining legal context
- Generate shareable prompt templates that users can modify
- Deep links to Gemini/ChatGPT sites with context parameters

### Out of Scope
- Backend API modifications (existing context is sufficient)
- Direct API integration with Gemini/ChatGPT from frontend (use URLs instead)
- User authentication for external services
- Storing external chat history in our system

## Context Requirements

1. **Frontend Stack**: Next.js (existing) with React components
2. **Legal Context**: Retrieved documents, citations, query classification
3. **External Services**:
   - Gemini: https://gemini.google.com (no URL param API)
   - ChatGPT: https://chatgpt.com (no URL param API)
4. **Prompt Templates**: Pre-built Vietnamese legal context prompts

## Success Metrics

- User can click button and open external AI chat with context
- Prompt includes original query, document references, and legal domain
- Clear visual indication that user is leaving our app
- Works on desktop and mobile (responsive design)

## Technical Considerations

1. **Copy-to-Clipboard**: Primary approach—format context, copy to clipboard, open external site
2. **URL Encoding**: If using URL parameters, ensure proper Vietnamese text encoding
3. **Privacy**: Document URIs should be source references, not full URLs
4. **State Management**: Use existing chat history + retrieval results context

## Assumptions

- Users have access to Gemini and/or ChatGPT
- External services accept large prompt contexts
- Vietnamese legal terminology translates to these services sufficiently

---
*Created: 2026-05-25 as Phase 20 — Frontend AI Chat Integration*

