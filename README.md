# StockAI v2 — 系統重構

## 背景
大佬 approved Option A (一次性重構)。Legacy v1.7 tagged as `legacy/v1.7` on GitHub.

## Tech Stack
- **Frontend**: React 19 + Next.js 15 + Tailwind CSS v4 + TypeScript 5.x
- **Backend**: FastAPI (Python 3.12+) + PostgreSQL + Redis
- **Auth**: JWT RS256 + Refresh Rotation + RBAC
- **Real-time**: WebSocket (Redis Pub/Sub)
- **i18n**: next-intl (繁/簡/英)

## Architecture
```
Client → TLS → Cloudflare → Nginx → FastAPI
                                        ├── WebSocket (Redis)
                                        └── PostgreSQL (Audit)
```

## Phases
| Phase | Content | Status |
|-------|---------|--------|
| 0 | Codebase freeze + project scaffold | ✅ Done |
| 1 | Backend API (FastAPI + PostgreSQL) | ⏳ |
| 2 | Dashboard UI (React + Next.js) | ⏳ |
| 3 | Auth + Security | ⏳ |
| 4 | Charts + Capital Flow + AI Signals | ⏳ |
| 5 | Testing + Compliance | ⏳ |

## 大佬 Conditions
1. ✅ Master cleanup done
2. ⬜ Each Phase: 大佬 UAT sign-off required
3. ⬜ Documentation同步寫
