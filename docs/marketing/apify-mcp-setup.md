# Apify MCP × Claude 데스크톱 설치 가이드

이 문서는 영상에서 소개한 "Claude 하나로 실시간 웹 데이터(유튜브·인스타그램·구글)를 검색·분석"하는 세팅을 본인 PC에서 직접 따라 할 수 있도록 정리한 것입니다. Apify의 MCP(Model Context Protocol) 서버를 Claude 데스크톱 앱에 연결하면, 채팅 안에서 Apify의 스크래퍼(Actor)들을 도구처럼 호출해 실시간 데이터를 가져올 수 있습니다.

이 저장소에 함께 들어 있는 예시 파일:

- `claude_desktop_config.example.json` — npx 로 로컬 실행하는 방식(토큰을 env 로 넣음)
- `claude_desktop_config.remote.example.json` — Apify 호스팅 원격 엔드포인트 방식(OAuth 또는 헤더 토큰)

두 방식 중 **원격(remote) 방식을 권장**합니다. Node/npx 설치가 필요 없고, 최신 Claude 데스크톱에서는 토큰을 파일에 적지 않고 브라우저 OAuth 로그인으로 끝낼 수 있어 더 안전합니다. npx 방식은 사내 정책 등으로 원격 연결이 막혔거나, 실행 옵션을 세밀하게 제어하고 싶을 때 쓰세요.

> 참고: 데스크톱 앱 설치, Apify 토큰 발급, OAuth 로그인 클릭은 모두 **본인 PC와 본인 계정에서만** 할 수 있는 작업입니다. 이 가이드는 그 단계를 대신해 주지 않고, 그대로 따라 할 수 있게 안내만 합니다.

---

## 0. 준비물

- **Claude 데스크톱 앱** (Mac 또는 Windows). claude.ai 에서 다운로드.
- **Apify 계정**. https://apify.com 에서 무료 가입 가능. 무료 크레딧이 매월 제공되며, 스크래핑 사용량만큼 과금됩니다.
- (npx 방식만) **Node.js LTS** 설치. 원격 방식을 쓰면 필요 없습니다.

## 1. Apify 토큰 발급 (npx·헤더 방식에만 필요)

1. Apify 콘솔 로그인 → 우측 상단 프로필 → **Settings → API & Integrations**.
2. **Personal API token** 을 복사합니다. (`apify_api_...` 형태)
3. 이 토큰은 비밀번호와 같습니다. **공개 저장소·메신저·스크린샷에 노출 금지.**

원격 OAuth 방식을 쓸 거라면 이 단계는 건너뛰어도 됩니다. 첫 연결 때 브라우저 로그인으로 인증합니다.

## 2. Claude 데스크톱에 MCP 연결하기

### 방식 A — 원격 엔드포인트 (권장)

최신 Claude 데스크톱에는 "커넥터(Connectors)" 메뉴가 있습니다.

1. Claude 데스크톱 → **Settings → Connectors → Add custom connector**.
2. 서버 URL 에 다음을 입력:
   ```
   https://mcp.apify.com
   ```
3. 저장 후 연결을 켜면 브라우저가 열리며 Apify 로그인/승인 화면이 뜹니다. 승인하면 끝.

커넥터 메뉴가 없는 구버전이라면, 아래 설정 파일 방식으로 `claude_desktop_config.remote.example.json` 내용을 사용하세요.

### 방식 B — 설정 파일 직접 편집

1. Claude 데스크톱 → **Settings → Developer → Edit Config** 를 누르면 `claude_desktop_config.json` 파일 위치가 열립니다.
   - Mac: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - Windows: `%APPDATA%\Claude\claude_desktop_config.json`
2. 이 저장소의 예시 파일 내용을 그 파일에 복사합니다.
   - npx 로컬 실행 → `claude_desktop_config.example.json`
   - 원격(헤더 토큰) → `claude_desktop_config.remote.example.json`
   - 두 예시 모두 맨 위 `_comment` 키는 설명용이니 실제 설정에서는 지워도 됩니다. `_headers_example` 도 마찬가지로 참고용입니다.
3. `<APIFY_TOKEN>` 자리에 1단계에서 복사한 본인 토큰을 붙여 넣습니다.
4. 파일을 저장하고 **Claude 데스크톱을 완전히 종료 후 재실행**합니다.

## 3. 어떤 도구(Actor)를 켤지

예시 설정에는 마케팅 리서치에 바로 쓸 수 있는 Actor를 미리 넣어 두었습니다:

| 도구 | 용도 |
| --- | --- |
| `actors`, `docs` | Apify 스토어의 Actor 검색·실행, 사용법 문서 조회 (기본 도구) |
| `apify/rag-web-browser` | 일반 웹페이지를 열어 본문을 읽어오는 범용 브라우저 (기본 도구) |
| `apify/instagram-scraper` | 인스타그램 게시물·릴스·프로필 데이터 |
| `streamers/youtube-scraper` | 유튜브 영상·채널 메타데이터 |
| `apify/google-search-scraper` | 구글 검색 결과 수집 |

도구 목록은 npx 방식의 `--tools` 인자, 원격 방식의 `?tools=` 쿼리 파라미터로 조절합니다. 아무것도 지정하지 않으면 `actors`, `docs`, `apify/rag-web-browser` 세 가지만 기본 활성화됩니다.

> Actor 이름(예: `streamers/youtube-scraper`)은 Apify 스토어에서 바뀌거나 더 적합한 대체 Actor가 있을 수 있습니다. 채팅에서 "유튜브 스크래퍼 Actor 찾아줘"처럼 `actors` 도구로 검색해 현재 가장 알맞은 것을 고르는 방법도 있습니다.

## 4. 연결 확인

1. Claude 데스크톱에서 새 대화를 엽니다.
2. 입력창 근처 도구(🔧 / 망치) 아이콘을 눌러 `apify` 관련 도구가 떠 있는지 확인합니다.
3. 간단히 테스트: "Apify로 '인테리어 광고' 구글 검색 상위 결과 5개만 가져와줘" 라고 요청해 데이터가 실제로 돌아오는지 봅니다. 첫 호출 시 Apify에서 Actor가 실행되며 약간의 시간이 걸릴 수 있습니다.

## 5. 비용·주의

- Apify는 스크래핑 사용량(컴퓨트 유닛, 결과 수)에 따라 과금됩니다. 무료 크레딧을 초과하면 비용이 발생하므로, 큰 범위 수집 전에 결과 개수를 제한(예: `maxItems`)하세요.
- 스크래핑 대상 사이트의 약관·로봇 정책을 확인하세요. 특히 인스타그램·유튜브 등은 수집 범위에 제약이 있을 수 있습니다.
- **토큰이 들어간 실제 `claude_desktop_config.json` 은 절대 git에 커밋하지 마세요.** 이 저장소에는 토큰 없는 예시(`*.example.json`)만 둡니다.

---

## 다음 단계

연결이 끝나면, 영상의 마케팅 워크플로우(광고 레퍼런스 분석 → 페르소나별 대본 → 이미지 프롬프트 → 랜딩페이지 → 영업 PPT)를 프롬프트로 굴리면 됩니다. 각 단계용 프롬프트 템플릿이 필요하면 별도로 정리해 드릴 수 있습니다.

## 출처

- [Apify MCP server — Apify Documentation](https://docs.apify.com/platform/integrations/mcp)
- [Claude Desktop integration — Apify Documentation](https://docs.apify.com/platform/integrations/claude-desktop)
- [apify/apify-mcp-server — GitHub](https://github.com/apify/apify-mcp-server)
- [Getting Started with Local MCP Servers on Claude Desktop — Claude Help Center](https://support.claude.com/en/articles/10949351-getting-started-with-local-mcp-servers-on-claude-desktop)
