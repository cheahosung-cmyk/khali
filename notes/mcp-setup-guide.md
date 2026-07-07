# Claude Code MCP 서버 설치 가이드

내가 쓰는 6개 도구(Notion·Slack·Google Drive·GitHub·Figma·Linear) 기준으로 정리한
MCP 서버 우선순위와 설치·보안 노트.

## 먼저 짚을 것

- MCP 서버는 로컬 머신의 Claude Code에 붙는다. 원격 세션에서는 대신 깔아줄 수 없다.
- 목록의 **Claude Code(1번)** 는 도구 자체, **Claude Code Action(24번)** 은 GitHub Action이라 MCP 서버가 아니다. 설치 대상에서 제외.
- 직무 칸은 비어 있으므로 실제 쓰는 6개 도구를 기준으로 우선순위를 짰다.
  데이터 분석이 주 직무면 PostgreSQL/SQLite가 Tier 2로, 개발이면 Git이 Tier 1로 올라온다.
- OS 차이는 거의 없다. `claude mcp add` 명령은 macOS·Linux·Windows 동일.
  Windows에서 `npx` 형이 안 뜨면 `-- cmd /c npx -y …` 로 래핑.

## 24개 후보 컷

| Tier | 항목 | 판정 | 이유 |
|---|---|---|---|
| 1 지금 깔기 | 6 GitHub | 설치 | 쓰는 도구, 코드/이슈/PR |
| | 18 Notion | 설치 | 쓰는 도구, 문서·DB 허브 |
| | 17 Slack | 설치 | 쓰는 도구, 대화·검색 |
| | 19 Linear | 설치 | 쓰는 도구, 이슈 트래킹 |
| | 3 Filesystem | 설치 | 로컬 파일 작업 기반 |
| | 12 Context7 | 설치 | 최신 라이브러리 문서 조회 |
| 2 도구/직무 맞으면 | 20 Figma | 조건부 | Figma 데스크톱 + Dev seat 필요 |
| | 16 Google Drive | 조건부 | OAuth 셋업 무겁고 권한 큼 |
| | 9 Playwright | 조건부 | 웹 자동화/테스트/스크래핑 |
| | 10 Firecrawl | 조건부 | 웹페이지→마크다운 대량 크롤 |
| | 13 Fetch | 조건부 | URL 한 개 가볍게 읽기(무키) |
| | 7 Git | 조건부 | 로컬 저장소. 개발 직무면 Tier 1 |
| 3 특정 상황만 | 8 Perplexity / 14 Brave / 15 Exa | 택1 | 웹검색은 하나만 |
| | 21 PostgreSQL / 22 SQLite | 조건부 | 데이터 분석 + 실제 그 DB 쓸 때만 |
| | 4 Memory / 5 Sequential Thinking | 보류 | 효과 애매 |
| | 23 Docker | 위험 | 컨테이너 직접 관리할 때만. 권한 최상위 |
| 설치 안 함 | 1 Claude Code | 제외 | 도구 자체 |
| | 24 Claude Code Action | 제외 | MCP 아님(GitHub Action) |
| | 2 Chrome MCP | 제외 | Playwright와 중복 |
| | 11 Glif | 제외 | 니치 |

핵심 쟁점: (a) 검색 서버는 하나면 충분 — 셋 다 깔면 혼란·키 낭비. (b) GitHub·Notion·Linear·Figma는
호스팅형 OAuth가 있어 API 키를 직접 보관 안 해도 된다 → 이쪽 권장. (c) 다 깔지 말 것 — 많을수록
컨텍스트 무겁고 권한 표면 넓어진다. Tier 1 여섯 개로 시작.

## Tier 1 상세

| 서버 | API 키 | 설치 명령 | 첫 테스트 | 조심할 권한 |
|---|---|---|---|---|
| Filesystem | 불필요 | `claude mcp add filesystem -- npx -y @modelcontextprotocol/server-filesystem ~/projects` | "~/projects 파일 목록" | 범위를 지정 폴더로 한정. 홈/루트 통째 금지 |
| Context7 | 불필요 | `claude mcp add context7 -- npx -y @upstash/context7-mcp` | "Next.js 15 App Router 최신 라우팅 예제" | 라이브러리명만 외부로. 위험 낮음 |
| GitHub | PAT/OAuth | `claude mcp add --transport http github https://api.githubcopilot.com/mcp/` | "khali의 열린 PR 목록" | PAT는 fine-grained, 필요한 repo만 |
| Notion | OAuth | `claude mcp add --transport http notion https://mcp.notion.com/mcp` | "이번 주 회의록 요약" | 특정 페이지/DB만 공유 |
| Slack | Bot Token + Team ID | `claude mcp add slack -e SLACK_BOT_TOKEN=xoxb-… -e SLACK_TEAM_ID=T… -- npx -y @modelcontextprotocol/server-slack` | "#general 오늘 대화 3줄 요약" | 봇을 필요한 채널에만 초대 |
| Linear | OAuth | `claude mcp add --transport sse linear https://mcp.linear.app/sse` | "나한테 배정된 이슈 우선순위 순" | 스코프 확인. 이슈 생성·수정 가능 |

Claude Desktop용 `.mcp.json` 포맷 예:

```json
{
  "mcpServers": {
    "context7": { "command": "npx", "args": ["-y", "@upstash/context7-mcp"] }
  }
}
```

## 보안 공통

- 가장 큰 위험은 프롬프트 인젝션. 웹/Slack/Notion에서 읽어온 텍스트에 숨은 지시가
  쓰기 권한 서버(Filesystem·GitHub·Docker)와 결합되면 실제 피해로 이어진다.
  읽기용·쓰기용을 둘 다 강한 권한으로 열어두지 말 것.
- `.mcp.json`에 평문 키를 넣고 git에 커밋하지 말 것. `-e KEY=$ENV_VAR` 환경변수 참조,
  또는 호스팅 OAuth가 있는 서버는 애초에 키를 로컬에 안 둔다.
- 권한 위험도 순: Docker > Filesystem 광범위 스코프 > GitHub 전체권한 PAT >
  Google Drive 전체 스코프 > Slack 봇 과다 초대.

## 붙인 링크 매핑

- perplexityai/modelcontextprotocol → 8 Perplexity (검색, 택1)
- firecrawl/firecrawl-mcp-server → 10 Firecrawl (Tier 2)
- upstash/context7 → 12 Context7 (Tier 1)
- microsoft/playwright-mcp → 9 Playwright (Tier 2)
- modelcontextprotocol/servers → 공식 모음집(Filesystem·Fetch·Git·Memory·Sequential 등)
- anthropics/claude-code-action → 24번, MCP 아님(제외)

> 호스팅 엔드포인트와 npm 패키지명은 자주 바뀌므로 실행 전 각 저장소 README로 현재 명령을 대조할 것.
