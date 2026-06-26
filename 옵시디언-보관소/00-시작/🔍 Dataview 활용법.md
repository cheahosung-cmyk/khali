---
title: Dataview 활용법
tags:
  - 가이드
  - 플러그인
  - dataview
---

# 🔍 Dataview 활용법

Dataview는 노트들을 **자동으로 표·목록·할 일 모음**으로 만들어 주는 플러그인입니다. 직접 정리하지 않아도 조건에 맞는 노트가 알아서 모입니다.

## 1. 설치
`설정 → 커뮤니티 플러그인 → 제한 모드 끄기 → "Dataview" 검색 → 설치 → 활성화`

설치 후 [[🏠 마스터 옵시디언 - 시작하기]] 대시보드가 자동으로 채워집니다.

## 2. 기본 문법

코드 블록 언어를 ` ```dataview ` 로 시작합니다.

### 목록으로
````
```dataview
LIST
FROM "10-노트"
SORT file.mtime DESC
```
````

### 표로
````
```dataview
TABLE file.mtime AS "수정일", file.tags AS "태그"
FROM "30-자료"
SORT file.mtime DESC
```
````

### 할 일만 모으기
````
```dataview
TASK
WHERE !completed
```
````

### 특정 태그만
````
```dataview
LIST
FROM #프로젝트
```
````

## 3. 자주 쓰는 조건(WHERE)

| 조건 | 의미 |
|---|---|
| `WHERE !completed` | 끝나지 않은 할 일만 |
| `WHERE contains(file.name, "회의")` | 제목에 "회의" 포함 |
| `WHERE file.mtime >= date(today) - dur(7 days)` | 최근 7일 수정 |
| `WHERE 별점 >= 4` | 속성 `별점`이 4 이상 |

## 4. 인라인 필드(메타데이터)

노트에 `상태:: 진행중` 처럼 적으면 Dataview가 `상태` 값을 읽습니다. (`::` 두 개)
또는 노트 맨 위 `---` 프론트매터의 `tags`, `별점` 등을 그대로 활용합니다.

> [!tip]
> 처음엔 [[🏠 마스터 옵시디언 - 시작하기]]의 쿼리를 복사해 폴더 이름만 바꿔 써보세요.

← [[🏠 마스터 옵시디언 - 시작하기]]
