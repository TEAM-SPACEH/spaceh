# spaceH 디자인 시스템 및 UI 가이드라인 (`design.md`)

> **문서 목적**: 본 문서는 **spaceH (현대 계열사 통합 지능형 문서 검색 플랫폼)**의 UI/UX 일관성을 확립하고, AI 에이전트 및 개발자가 프론트엔드(Streamlit 기반 `views/`) 구현 시 반드시 준수해야 하는 디자인 원칙과 구현 명세를 정의한다.

---

## 1. 디자인 철학 및 기본 원칙 (Design Philosophy)

Anthropic의 `frontend-design` 가이드라인과 현대 계열사의 브랜드 아이덴티티를 계승하여 **"Generic AI Slop(무의미한 템플릿과 그라디언트 남발)"을 전면 배제**하고, 엔터프라이즈 환경에 최적화된 높은 신뢰도와 가독성을 지향한다.

### 1.1 핵심 가치
1. **도메인 특화성 (Subject-Matter Grounding)**:
   - spaceH는 현대경제연구원·현대무벡스·현대엘리베이터 임직원이 사용하는 사내 지식 검색 및 의사결정 인텔리전스 플랫폼이다.
   - 가볍거나 장난스러운 요소를 배제하고, 금융·물류·엔지니어링 보고서의 권위와 신뢰성을 전달하는 단정하고 명확한 비즈니스 룩을 구축한다.
2. **엄격한 시각적 위계 (Rigid Hierarchy)**:
   - 흑백 기반의 높은 대비(Contrast)를 기본으로 하고, 브랜드 컬러는 명확한 기능적 목적이 있을 때만 엄격하게 통제하여 사용한다.
3. **정보 밀도와 여백의 조화 (Compact Density & Breathable Space)**:
   - 전문적인 문서 요약, 각주 인용 등 고밀도 데이터를 사용자가 피로감 없이 빠르게 스캔할 수 있도록 8px 기준 그리드와 정돈된 카드 구조를 유지한다.
4. **권한과 보안의 직관적 시각화 (Security Visibility)**:
   - 문서마다 보안 등급(전사 public, 자사 internal, 타사 internal)과 계열사 소속을 명확히 노출하여 보안 사고를 예방하고 사용자의 접근 권한 상태를 한눈에 파악하게 한다.

---

## 2. 컬러 시스템 (Color System & Palette)

기본 원칙: **하얀 배경(#FFFFFF)에 검정 글씨(#111111)를 바탕으로 하며, 브랜드 3색의 위계(#009944 > #FABE00 > #004098)를 엄격히 준수한다.**

### 2.1 베이스 뉴트럴 (Base Neutrals)
| 토큰명 | HEX | 역할 |
|---|---|---|
| `bg-primary` | `#FFFFFF` | 메인 캔버스 배경, 카드 배경 |
| `bg-secondary` | `#F8F9FA` | 사이드바 배경, 코드 블록, 비활성 탭 |
| `bg-tertiary` | `#F1F3F5` | 호버 상태, 테이블 헤더, 경계 영역 |
| `border-light` | `#E9ECEF` | 미세한 구분선, 카드 테두리 |
| `border-medium` | `#CED4DA` | 인풋 필드 테두리, 드롭다운 테두리 |
| `text-primary` | `#111111` | 기본 본문 텍스트, H1~H4 제목 (최대 대비) |
| `text-secondary`| `#495057` | 메타데이터, 부제목, 라벨 |
| `text-muted` | `#868E96` | 플레이스홀더, 힌트 텍스트, 풋노트 번호 |

### 2.2 브랜드 컬러 및 사용 규칙 (60-30-10 원칙)
| 브랜드 토큰 | HEX | 역할 및 사용 원칙 |
|---|---|---|
| **Primary (메인)** | `#009944` | **현대 그린 (Main Brand)**<br>- 메인 CTA 버튼 (검색, 보고서 생성)<br>- 선택된 탭 및 활성 네비게이션 인디케이터<br>- 주요 시스템 확인 상태 아이콘<br>- 전체 UI 액센트의 약 70% 비중 |
| **Accent 1 (1순위 포인트)**| `#FABE00` | **현대 옐로우 (Priority Accent)**<br>- 시선 집중 포인트, 북마크 아이콘 활성화<br>- RAG 근거 문장 하이라이트 배경 tint (연하게 투명도 적용: `rgba(250, 190, 0, 0.15)`)<br>- 주의(Warning) 알림 배지, 요약 핵심 키워드 칩 |
| **Accent 2 (2순위 포인트)**| `#004098` | **현대 블루 (Secondary Accent)**<br>- 텍스트 링크, 문서 열람(원문 보기) 보조 버튼<br>- 정보성(Info) 알림 배지, 시스템 설정 아이콘<br>- 계열사 구분 시 신뢰성 상징 메타 태그 |

### 2.3 문서 보안 등급 뱃지 컬러 (Security Classification)
문서의 보안 등급은 **열람자의 소속 계열사 기준**으로 3가지 상태로 표시한다.
- **public (전사)**: 배경 `#EBFBEE`, 텍스트/보더 `#2B8A3E` (전 계열사 임직원 열람 가능)
- **internal · 자사**: 배경 `#E7F5FF`, 텍스트/보더 `#1971C2` (열람자와 같은 계열사 문서, 같은 계열사 임직원만 열람 가능)
- **internal · 타사**: 배경 `#FFF5F5`, 텍스트/보더 `#E03131` (다른 계열사의 internal 문서, 열람 제한/권한 요청 대상)

### 2.4 사용자 역할 (Role)
| 역할 | 표시명 | 열람 범위 |
|---|---|---|
| `employee` | 일반사원 | 전사 public + 자사 internal |
| `company_admin` | 계열사 관리자 | 전사 public + 자사 internal (자사 문서의 권한 관리) |
| `super_admin` | 최종 어드민 | 전사 public + 자사·타사 internal 전체 |

---

## 3. 타이포그래피 시스템 (Typography)

spaceH의 서체는 현대 브랜드 전용 폰트 2종을 기반으로 설계된다.

### 3.1 폰트 패밀리 지정
```css
/* 기본 폰트 스택 */
font-family: "NeoHyundai", "Marine", -apple-system, BlinkMacSystemFont, "Pretendard", "Segoe UI", Roboto, sans-serif;
```
- `"NeoHyundai"`, `"Marine"`은 시스템 설치 폰트에 의존하지 않고 **`@font-face`로 직접 제공**한다. 폰트 파일은 `app/static/fonts/`에 두고 `.streamlit/config.toml`의 `[server] enableStaticServing = true`로 서빙한다 (구현 예시는 7장 참조).
- `"Pretendard"` 등은 폰트 로딩 실패 시를 위한 fallback이며, 두 브랜드 폰트를 대체하지 않는다.
1. **메인 서체: `"NeoHyundai"`**
   - **용도**: 제목(Heading), 본문(Body), 입력 폼, UI 전반의 한국어 텍스트.
   - **특징**: 단단한 골격과 정직한 인상을 주어 기업 공식 문서 및 데이터 표현에 안정감을 부여.
2. **보조/영문 서체: `"Marine"`**
   - **용도**: 영문 로고 타이틀, 숫자 통계(KPI/지표), 헤더 메타데이터, 코드/각주 번호.
   - **특징**: 모던하고 날렵한 비즈니스 감성을 제공하며 숫자의 판독성이 우수함.

### 3.2 타이포그래피 스케일 & 스펙
| 토큰 | 크기 | Line Height | Weight | 적용처 |
|---|---|---|---|---|
| `text-display` | 28px (1.75rem) | 1.3 | Bold (700) | 메인 랜딩 타이틀, 대시보드 메인 카운터 |
| `text-h1` | 22px (1.375rem) | 1.35 | Bold (700) | 페이지 제목 (통합 문서 검색, 종합 보고서) |
| `text-h2` | 18px (1.125rem) | 1.4 | SemiBold (600) | 섹션 헤더, 문서 카드 제목, 모달 타이틀 |
| `text-h3` | 15px (0.9375rem) | 1.45 | Medium (500) | 카드 서브헤더, 필터 그룹 라벨, 탭 라벨 |
| `text-body` | 14px (0.875rem) | 1.6 | Regular (400) | 본문 텍스트, 검색 결과 요약문, 챗봇 답변 |
| `text-caption` | 12px (0.75rem) | 1.5 | Regular (400) | 메타데이터 (작성일, 작성자), 뱃지, 각주 |

---

## 4. 레이아웃 & 공간 구성 원칙 (Spatial Composition)

### 4.1 8px 베이스 그리드 (Spacing System)
- `spacing-xs`: 4px (미세 요소 정렬, 인라인 태그 내부)
- `spacing-sm`: 8px (컴포넌트 내부 여백, 아이콘과 텍스트 간격)
- `spacing-md`: 16px (기본 패딩, 카드 내부 여백, 입력 필드 간격)
- `spacing-lg`: 24px (카드 간 간격, 섹션 내부 컨테이너 간격)
- `spacing-xl`: 32px (주요 섹션 간 구분)

### 4.2 Streamlit 뷰 구조화 (Page Layout)
```text
+-----------------------------------------------------------------------+
| [GNB] spaceH 로고 | [통합 현황] | [내 역할: employee · 현대무벡스] | 사용자정보 |
+------------------+----------------------------------------------------+
| [사이드바 필터]     | [메인 워크스페이스]                                     |
| - 검색어 입력      |  - 탭: [자연어 통합 검색] [종합 보고서]     |
| - 계열사 다중선택  |  ------------------------------------------------- |
| - 기간/포맷 필터   |  [컨텐츠 영역: 고밀도 카드 그리드]            |
| - 보안 등급 필터   |  ------------------------------------------------- |
|                  |  [AI 답변 및 인용 출처 드로어/원문 뷰어]                    |
+------------------+----------------------------------------------------+
```

---

## 5. 핵심 UI 컴포넌트 명세 (Components)

### 5.1 버튼 (Buttons)
- **Primary Button**:
  - 배경 `#009944`, 텍스트 `#FFFFFF`, 보더 없음, `border-radius: 4px;`
  - Hover 시 `#007A36`, Active 시 `#005C29`
  - 용도: 검색 실행, 보고서 생성, 확인
- **Secondary / Outline Button**:
  - 배경 `#FFFFFF`, 텍스트 `#009944`, 보더 `1px solid #009944`
  - Hover 시 배경 `#F0FDF4`
  - 용도: 필터 초기화, 원문 보기, 취소
- **Action / Link Button**:
  - 배경 투명, 텍스트 `#004098`, Underline on hover
  - 용도: 출처 각주 클릭, 권한 요청 링크
- **Streamlit 매핑**: `st.button(type="primary")` → Primary, `type="secondary"` → Outline, `type="tertiary"` → Link. 변형은 `button[kind=...]` 선택자로 구분하고, `.stButton > button`은 공통 기본(Primary) 스타일로 유지한다.

### 5.2 검색 결과 카드 (Document Card)
- **외관**: 배경 `#FFFFFF`, 테두리 `1px solid #E9ECEF`, `border-radius: 6px`, 내부 여백 `16px`.
- **호버 효과**: `border-color: #009944; box-shadow: 0 2px 8px rgba(0, 153, 68, 0.08);` (과한 3D 입체 효과 금지).
- **구성**:
  1. 헤더: [계열사 뱃지] + [보안 등급 뱃지] + 작성일자 (우측 정렬)
  2. 타이틀: `text-h2` (18px, Bold, `#111111`)
  3. 본문/스니펫: `text-body` (14px, `#495057`, 검색 키워드는 `#FABE00` 연한 하이라이트)
  4. 푸터: 관련 부서, 파일 포맷 아이콘, [원문 보기] 버튼

### 5.3 AI 근거 답변 및 각주 (Footnote & Citation)
- **답변 블록**:
  - 배경 `#F8F9FA`, 테두리 좌측 4px 현대 그린(`border-left: 4px solid #009944;`).
  - LLM 생성 텍스트는 명확한 불릿 포인트와 강조(Bold) 처리.
- **인용 각주 (Citation Badge)**:
  - 표기: `[1]`, `[2]` 형태의 인라인 뱃지.
  - 스타일: 배경 `#E7F5FF`, 텍스트 `#004098`, 클릭 시 우측에 원문 청크 팝오버/슬라이드 노출.

### 5.4 권한 제한 문서 표시 (M-03 연계)
- 열람 권한이 없는 문서(타사 internal을 `employee`·`company_admin`이 조회하는 경우)는 검색 목록에서 완전히 제외(사전 필터링)하는 것이 기본 원칙(S-03).
- 단, 메타데이터만 열람 가능한 경우:
  - 카드 배경 `#F8F9FA`, 제목 옆에 자물쇠 아이콘(🔒)만 표시한다. 제목은 흐림 처리 없이 일반 카드와 동일하게 노출한다.
  - 우측 하단에 **[열람 권한 요청]** 버튼 (`#FABE00` 바탕의 세컨더리 CTA) 배치.

---

## 6. Figma Dev Mode 분석 기반 보완점 (Figma vs. Streamlit)

Figma 원본(`Space-H #1-2`)의 정적 그래픽을 Streamlit 애플리케이션으로 옮길 때 발생하는 격차와 그에 대한 해결책은 다음과 같다:

| Figma 디자인 요소 | 발생 가능한 문제점 (Streamlit) | 보완 구현 원칙 (Solutions) |
|---|---|---|
| **기본 Streamlit 테마 누출** | Streamlit 기본 붉은색 테마 및 불필요한 상단 햄버거 메뉴/푸터 노출 | `.streamlit/config.toml`에 primaryColor를 `#009944`로 지정하고, CSS injection으로 Streamlit 기본 헤더/푸터 숨김 처리 |
| **커스텀 폰트 렌더링** | 로컬 폰트("NeoHyundai", "Marine") 미설치 클라이언트 환경에서 Pretendard 등으로 대체됨 | `app/static/fonts/`의 폰트 파일을 `@font-face`(`local()` 우선, `url()` 보조)로 선언해 클라이언트 설치 여부와 무관하게 제공하고, `Pretendard`·`Segoe UI`·`sans-serif`는 fallback으로만 사용 |
| **대시보드 카드 간격 불균형** | `st.container()` 사용 시 불필요하게 늘어지는 세로 여백 | 커스텀 CSS 클래스(`.spaceh-card`)를 선언하여 `padding: 16px; margin-bottom: 12px;`로 여백 통제 |
| **RAG 인용 출처 상호작용** | 텍스트 내 각주 클릭 시 전체 페이지가 리로드되는 현상 | `st.popover` 또는 탭/사이드바 토글을 활용하여 페이지 재실행 없이 출처 본문 즉시 확인 지원 |

---

## 7. Streamlit 구현 템플릿 (Code Snippets)

에이전트가 `views/` 화면을 작성할 때 최상단에서 불러올 공통 스타일 주입 예시:

```python
# app/views/components/styles.py
import streamlit as st

def apply_spaceh_theme():
    """spaceH 공통 디자인 테마 CSS 주입"""
    st.markdown(
        """
        <style>
        /* 1. 폰트 및 기본 캔버스 설정 */
        /* 브랜드 폰트: 설치본(local) 우선, 없으면 정적 서빙 파일 사용 */
        @font-face {
            font-family: "NeoHyundai";
            src: local("NeoHyundai"), url("app/static/fonts/NeoHyundai-Regular.woff2") format("woff2");
            font-weight: 400;
            font-display: swap;
        }
        @font-face {
            font-family: "NeoHyundai";
            src: local("NeoHyundai Bold"), url("app/static/fonts/NeoHyundai-Bold.woff2") format("woff2");
            font-weight: 700;
            font-display: swap;
        }
        @font-face {
            font-family: "Marine";
            src: local("Marine"), url("app/static/fonts/Marine-Regular.woff2") format("woff2");
            font-weight: 400;
            font-display: swap;
        }
        @font-face {
            font-family: "Marine";
            src: local("Marine Bold"), url("app/static/fonts/Marine-Bold.woff2") format("woff2");
            font-weight: 700;
            font-display: swap;
        }
        /* Pretendard는 fallback 전용 */
        @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
        
        html, body, [class*="css"] {
            font-family: "NeoHyundai", "Marine", "Pretendard", -apple-system, sans-serif;
            color: #111111;
            background-color: #FFFFFF;
        }

        /* 2. Streamlit 기본 헤더/푸터 정리 */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}

        /* 3. 버튼 스타일: 기본(Primary) + 변형(Outline, Link) */
        .stButton > button {
            background-color: #009944;
            color: #FFFFFF;
            border-radius: 4px;
            border: none;
            font-weight: 600;
            padding: 8px 16px;
            transition: all 0.2s ease;
        }
        .stButton > button:hover {
            background-color: #007A36;
            color: #FFFFFF;
            box-shadow: 0 2px 6px rgba(0, 153, 68, 0.2);
        }
        .stButton > button:active {
            background-color: #005C29;
        }
        /* Secondary / Outline */
        .stButton > button[kind="secondary"] {
            background-color: #FFFFFF;
            color: #009944;
            border: 1px solid #009944;
        }
        .stButton > button[kind="secondary"]:hover {
            background-color: #F0FDF4;
            color: #009944;
            box-shadow: none;
        }
        /* Action / Link */
        .stButton > button[kind="tertiary"] {
            background-color: transparent;
            color: #004098;
            border: none;
            padding: 0;
        }
        .stButton > button[kind="tertiary"]:hover {
            background-color: transparent;
            color: #004098;
            text-decoration: underline;
            box-shadow: none;
        }

        /* 4. 카드 컨테이너 */
        .spaceh-card {
            background-color: #FFFFFF;
            border: 1px solid #E9ECEF;
            border-radius: 6px;
            padding: 16px;
            margin-bottom: 12px;
            transition: border-color 0.2s;
        }
        .spaceh-card:hover {
            border-color: #009944;
        }

        /* 5. 인용 하이라이트 */
        .citation-highlight {
            background-color: rgba(250, 190, 0, 0.15);
            padding: 2px 4px;
            border-radius: 3px;
            font-weight: 500;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
```

---

## 8. 에이전트 UI 생성 가드레일 (Agent Guardrails)

AI 에이전트가 새로운 UI를 생성하거나 기존 코드를 수정할 때 다음 2-Pass 점검 프로세스를 거쳐야 한다:

### 8.1 1-Pass: 계획 수립 (Design Check)
- [ ] 배경이 순백색(`#FFFFFF`) 또는 연한 그레이(`#F8F9FA`)인가?
- [ ] 주요 동작 버튼에 `#009944`(현대 그린)가 적용되었는가?
- [ ] 포인트 컬러로 `#FABE00`(노랑)과 `#004098`(파랑)이 올바른 우선순위와 목적에 맞게 쓰였는가?
- [ ] 폰트 스택에 `"NeoHyundai"`와 `"Marine"`이 최우선으로 선언되었는가?
- [ ] 계열사 및 보안 등급 뱃지가 명확한 시각적 대비를 제공하는가?

### 8.2 절대 금지 사항 (Strictly Forbidden)
1. ❌ **보라색/인디고/핑크 그라디언트 금지**: AI 생성 템플릿의 전형적인 보라 계열 그라디언트는 일체 불허한다.
2. ❌ **다크 모드 혼용 금지**: 일관성을 위해 기본 배경은 무조건 라이트 캔버스(#FFFFFF)로 통일한다.
3. ❌ **인라인 복합 CSS 난립 금지**: 컴포넌트마다 제각각 style 속성을 주지 말고 공통 클래스(`styles.py`)를 재사용한다.
4. ❌ **모호한 플레이스홀더 금지**: "내용을 입력하세요" 대신 "현대무벡스 3분기 스마트팩토리 실적 보고서 검색"과 같은 구체적인 도메인 예시를 제공한다.

