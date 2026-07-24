# Reactor Tag Reconstruction - 2026-07-07

This record captures the Python/Reactor `v1.0.*` tag cleanup performed after
`v1.0.0`. Legacy `spring-v*` tags were intentionally preserved because they
represent the old Spring/Kotlin product line.

## Decision

- Keep `v1.0.0` as the Python/FastAPI/LangGraph initial release.
- Replace the dense `v1.0.1` through `v1.0.255` sequence with milestone tags.
- Do not tag current `HEAD` because release readiness is still blocked by live
  preflight and LangSmith sync requirements.
- Do not create `v1.1.0` until a user-visible product/runtime capability
  boundary passes the release readiness gate.

## New Tag Map

| New tag | Previous anchor | Commit | Meaning |
| --- | --- | --- | --- |
| `v1.0.0` | `v1.0.0` | `b65fa038ad` | Python/FastAPI/LangGraph initial release |
| `v1.0.1` | `v1.0.10` | `4193f10e11` | Enterprise runtime hardening milestone |
| `v1.0.2` | `v1.0.17` | `279b9ae81d` | Protocol and API boundary lockdown |
| `v1.0.3` | `v1.0.23` | `59ea52b869` | Operator product workflow CLI checkpoint |
| `v1.0.4` | `v1.0.44` | `78e8e417af` | Framework-native runtime UX batch |
| `v1.0.5` | `v1.0.64` | `3ba4248396` | Framework-native product workflow batch |
| `v1.0.6` | `v1.0.95` | `52adfde21d` | Run diagnostics, RAG, and LangChain operator baseline |
| `v1.0.7` | `v1.0.114` | `222ac3bf30` | Smoke plan and LangSmith readiness fixture alignment |
| `v1.0.8` | `v1.0.122` | `b06e9991dc` | RAG candidate feedback workflow projection |
| `v1.0.9` | `v1.0.129` | `4effabec23` | Recovery and handoff identity baseline |
| `v1.0.10` | `v1.0.170` | `ad2d1d3b2c` | Slack event feedback persistence |
| `v1.0.11` | `v1.0.196` | `8f1fd8d2a6` | Release readiness and run action stabilization |
| `v1.0.12` | `v1.0.219` | `a1f608b123` | Concrete release tag recommendation handoff |
| `v1.0.13` | `v1.0.245` | `254bcdb693` | RAG ask after batch ingest workflow |
| `v1.0.14` | `v1.0.255` | `908b427da4` | Full local release contract lane |

## Current Untagged Work

At reconstruction time, `HEAD` was beyond the new latest release tag and remained
untagged because `reports/release-readiness.json` reported:

- `status=blocked`
- `recommendedVersionBump=none`
- `recommendedTagPattern=none`
- blockers: `preflight`, `langsmith_eval_sync`
