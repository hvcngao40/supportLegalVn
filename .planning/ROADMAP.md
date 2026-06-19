# Roadmap: supportLegal

## Milestones

- ✅ **v1.2 Quality Assurance** — Phases 1-6 (shipped 2026-04-26) [[Archive](milestones/v1.2-ROADMAP.md)]
- 🚧 **v2.0 Frontend & Chat** — Phases 6.1, 7-8 (planned)

## Phases

<details>
<summary>✅ v1.2 Quality Assurance (Phases 1-6) — SHIPPED 2026-04-26</summary>

- [x] Phase 1: Persistent Foundation — completed 2026-04-24
- [x] Phase 2: Full Scale Indexing — completed 2026-04-24
- [x] Phase 3: Smart Retrieval & RAG — completed 2026-04-26
- [x] Phase 4: Backend API Delivery — completed 2026-04-26
- [x] Phase 5: Hierarchical Structural Chunking — completed 2026-04-26
- [x] Phase 6: Retrieval Evaluation — completed 2026-04-26

</details>

### 🚧 v2.0 Frontend & Chat (Planned)

- [ ] Phase 6.1: Qwen-14B-Chat Classifier Provider (DashScope Primary, Ollama Backup) *(INSERTED)*
- [ ] Phase 6.1: Qwen-14B-Chat Classifier Provider (DashScope Primary, Ollama Backup)
- [x] Phase 6.2: DeepSeek API Classifier Integration (Replacing Qwen) — completed 2026-04-28
- [x] Phase 6.3: Groq (Llama-3) Classifier Provider (Fastest Latency) — completed 2026-04-28
- [x] Phase 06.4: Groq RAG Generator Integration (Replacing Gemini) — completed 2026-04-28
- [x] Phase 7: Frontend UI Integration — completed 2026-04-28
- [ ] Phase 8: Chat History & Feedback Loop
- [x] Phase 9: Production Deployment & Infrastructure (Vercel, EC2, Nginx) — completed 2026-05-06 [[Context](phases/09-production-deployment-infrastructure/09-CONTEXT.md)] [[Summary](phases/09-production-deployment-infrastructure/09-SUMMARY.md)]
- [ ] Phase 10: Article-Level Chunking & Full Re-index (Fix content truncation & speed)
- [x] Phase 11: Performance Testing & Monitoring (Query, Classifier, RAG, Rerank) — completed 2026-05-03
- [x] Phase 12: Legal Search API for Full Content Retrieval — completed 2026-05-03
- [x] Phase 13: Frontend Original Content Display with Highlights — completed 2026-05-04
- [x] Phase 14: Frontend Chat History Retention and RAG Context Loop — completed 2026-05-04
- [x] Phase 15: Cải thiện UI chuẩn ngành luật với Tag phân loại và Rerank — completed 2026-05-04
- [x] Phase 16: Stream API Integration (Chuyển /ask sang /stream) — completed 2026-05-05
- [x] Phase 17: API Gateway Layer (Bảo vệ API & Rate Limit) — completed 2026-05-05

### 🚧 v3.0 Production Scaling & Resilience (Planned)

- [x] Phase 18: Tối ưu RAG & Qdrant - Hiệu năng — completed 2026-05-05 [[Plan](file:///c:/Users/hvcng/PycharmProjects/supportLegalVn/.planning/phases/18-optimization-rag-qdrant-performance/18-PLAN.md)]
- [x] Phase 19: Redis Cache Deployment — completed 2026-05-24 [[Context](file:///c:/Users/hvcng/PycharmProjects/supportLegalVn/.planning/phases/19-redis-cache-deployment/19-CONTEXT.md)] [[Plan](file:///c:/Users/hvcng/PycharmProjects/supportLegalVn/.planning/phases/19-redis-cache-deployment/19-PLAN.md)] [[Implementation](file:///c:/Users/hvcng/PycharmProjects/supportLegalVn/.planning/phases/19-redis-cache-deployment/19-IMPLEMENTATION.md)]
- [ ] Phase 20: Frontend AI Chat Integration (Gemini & ChatGPT Reference) [[Context](file:///c:/Users/hvcng/PycharmProjects/supportLegalVn/.planning/phases/20-frontend-ai-chat-integration/20-CONTEXT.md)]
- [ ] Phase 21: Tích hợp LangSmith qua @traceable để theo dõi hệ thống, đo lường chi phí token và tốc độ [[Context](file:///c:/Users/hvcng/PycharmProjects/supportLegalVn/.planning/phases/21-t-ch-h-p-langsmith-qua-traceable-theo-d-i-h-th-ng-o-l-ng-chi/21-CONTEXT.md)] [[Plan](file:///c:/Users/hvcng/PycharmProjects/supportLegalVn/.planning/phases/21-t-ch-h-p-langsmith-qua-traceable-theo-d-i-h-th-ng-o-l-ng-chi/21-PLAN.md)]

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Foundation | v1.2 | 2/2 | Complete | 2026-04-24 |
| 2. Indexing | v1.2 | 2/2 | Complete | 2026-04-24 |
| 3. Smart RAG | v1.2 | 2/2 | Complete | 2026-04-26 |
| 4. Backend API | v1.2 | 2/2 | Complete | 2026-04-26 |
| 5. Hierarchical | v1.2 | 2/2 | Complete | 2026-04-26 |
| 6. Evaluation | v1.2 | 1/1 | Complete | 2026-04-26 |
| 6.1 Qwen Classifier Provider | v2.0 | 0/0 | Planned | - |
| 6.2 DeepSeek Classifier Provider | v2.0 | 2/2 | Complete | 2026-04-28 |
| 6.3 Groq Classifier Provider | v2.0 | 1/1 | Complete | 2026-04-28 |
| 6.4 Groq RAG Generator Integration | v2.0 | 1/1 | Complete | 2026-04-28 |
| 7. Frontend UI Integration | v2.0 | 1/1 | Complete | 2026-04-28 |
| 8. Chat History | v2.0 | 0/0 | Planned | - |
| 9. Production Deployment | v2.0 | 1/1 | Complete | 2026-05-06 |
| 10. Article-Level Chunking & Re-index | v2.0 | 1/2 | Planned | - |
| 11. Performance Testing & Monitoring | v2.0 | 12/12 | Complete | 2026-05-03 |
| 12. Legal Search API | v2.0 | 0/0 | Complete | 2026-05-03 |
| 13. Frontend Highlight | v2.0 | 2/2 | Complete | 2026-05-04 |
| 14. Chat History Context Loop | v2.0 | 4/4 | Complete | 2026-05-04 |
| 15. UI Legal Tags & Rerank | v2.0 | 2/2 | Complete | 2026-05-04 |
| 16. Stream API Integration | v2.0 | 0/0 | Complete | 2026-05-05 |
| 17. API Gateway Layer | v2.0 | 6/6 | Complete | 2026-05-05 |
| 18. Tối ưu RAG & Qdrant | v3.0 | 10/10 | Complete | 2026-05-05 |
| 19. Redis Cache Deployment | v3.0 | 5/5 | Complete | 2026-05-24 |
| 20. Frontend AI Chat Integration | v3.0 | 0/0 | Planned | - |
| 21. Tích hợp LangSmith | v3.0 | 1/1 | Planned | - |

---
*Last updated: 2026-06-19 — Phase 21 planned*
