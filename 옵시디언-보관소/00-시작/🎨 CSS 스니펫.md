---
title: CSS 스니펫
tags:
  - 가이드
  - 꾸미기
---

# 🎨 CSS 스니펫 (보관소 꾸미기)

> [!info] 적용 방법
> 1. `설정 → 모양(Appearance) → CSS 스니펫 → 폴더 열기`
> 2. 그 폴더에 `.css` 파일을 넣기
> 3. 옵시디언으로 돌아와 새로고침 버튼 → 스니펫 켜기

## 예시 1 — 본문 글자 키우기

```css
/* readable-line.css */
.markdown-preview-view,
.markdown-source-view {
  font-size: 17px;
  line-height: 1.7;
}
```

## 예시 2 — 콜아웃 강조

```css
/* callout-accent.css */
.callout {
  border-radius: 10px;
}
```

## 자주 쓰는 콜아웃(Callout) 문법

> [!note] 노트
> 일반 정보

> [!tip] 팁
> 유용한 조언

> [!warning] 주의
> 조심할 것

> [!quote] 인용
> 인용문

작성법:
```markdown
> [!tip] 제목
> 내용
```

> [!tip] 더 쉬운 방법
> CSS가 어렵다면 [[🧩 추천 플러그인]]의 **Style Settings** 플러그인 + 인기 테마(예: Minimal, Things)를 설치하면 메뉴 클릭만으로 꾸밀 수 있습니다.

← [[🏠 마스터 옵시디언 - 시작하기]]로 돌아가기
