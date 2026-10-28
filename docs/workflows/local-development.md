# 로컬 개발 환경 (OS별)

모두 **Python 3.11 + `.venv` + `requirements.txt`** 로 통일한다. conda나 다른 Python 버전은 쓰지 않는다. 프로젝트 경로에는 한글·공백이 없는 곳을 권장한다.

## 준비물

| 항목 | 버전 |
| --- | --- |
| Python | 3.11.x (3.12·3.13 사용 금지) |
| MySQL | 8.0.16 이상 (Week4 수업 설치본) |
| Git | 최신 |

## 처음 한 번

### macOS

```bash
python3.11 --version     # 없으면 python.org 설치 파일 또는 brew install python@3.11
git clone https://github.com/TEAM-SPACEH/spaceh.git
cd spaceh
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env      # 값 채우기
```

### Windows (PowerShell)

```powershell
py -3.11 --version        # 없으면 python.org에서 3.11 설치, "Add python.exe to PATH" 체크
git clone https://github.com/TEAM-SPACEH/spaceh.git
cd spaceh
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
copy .env.example .env
```

`Activate.ps1`에서 "스크립트를 실행할 수 없습니다" 오류가 나면 한 번만 실행한다.

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

cmd를 쓰면 가상환경은 `.venv\Scripts\activate.bat`으로 켠다.

### 확인

```bash
python --version   # Python 3.11.x
pip check          # No broken requirements found.
```

## 매일 실행

| OS | 가상환경 켜기 |
| --- | --- |
| macOS | `source .venv/bin/activate` |
| Windows PowerShell | `.venv\Scripts\Activate.ps1` |
| Windows cmd | `.venv\Scripts\activate.bat` |

```bash
git pull origin develop
pip install -r requirements.txt   # requirements.txt가 바뀌었을 때
streamlit run main.py             # 저장소 루트에서 실행 → http://localhost:8501
python -m unittest                # 테스트
```

`main.py`는 저장소 루트에 있어야 `app`·`core`·`models`를 import할 수 있다. `app/` 안에서 실행하지 않는다.

VS Code: `Ctrl/Cmd + Shift + P` → `Python: Select Interpreter` → `.venv`

## 패키지 추가 규칙

1. 수업에서 배운 기술인지, 표준 라이브러리로 안 되는지 먼저 확인한다. 그래도 필요하면 팀장에게 먼저 말한다.
2. 승인되면 `패키지==버전` 한 줄을 `requirements.txt`에 추가한다.
3. `chore:` PR로 따로 올리고, 머지되면 팀 채팅에 `pip install -r requirements.txt` 하라고 알린다.

`pip freeze > requirements.txt`는 쓰지 않는다. OS마다 다른 패키지가 섞인다.

## 업로드 상태 행의 브라우저 정렬 검사

화면 상태 행을 변경했다면 설치된 Chrome으로 검사한다. DB·API 호출 없이 실제 네오현대 폰트와 공통 HTML·CSS로 처리 중·완료·중복·실패, 폭 280·520px, 배율 100·125%의 16조건을 확인한다.

```bash
python -m scripts.check_upload_layout
# Chrome이 기본 경로에 없을 때:
python -m scripts.check_upload_layout --chrome "Chrome 실행 파일의 경로"
```

폰트 로딩 실패, 문구 잘림, 텍스트·스피너의 세로 중앙 오차가 0.5px를 넘으면 실패한다. 전체 Streamlit 모달의 배치·상호작용 검증은 별도로 수행한다.

## MySQL

```sql
CREATE DATABASE spaceh CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
```

테이블과 시드 계정을 만든다 (저장소 루트, 가상환경 켠 상태). `schema.sql`은 기존 테이블을 지우고 다시 만드니 데이터가 사라진다.

```bash
mysql -u root -p spaceh < db/schema.sql
mysql -u root -p spaceh < db/seed.sql
python -m scripts.seed_users        # .env의 SEED_DEFAULT_PASSWORD 필요
```

Windows PowerShell은 `<`를 못 쓰니 `Get-Content db/schema.sql | mysql -u root -p spaceh`로 실행한다. `SELECT VERSION();`이 8.0.16 미만이면 CHECK 제약이 무시되니 팀장에게 알린다.

## 자주 나는 문제

| 증상 | 해결 |
| --- | --- |
| `ModuleNotFoundError: app` / `core` | 저장소 루트에서 `streamlit run main.py`로 실행했는지, 가상환경이 켜졌는지 확인 |
| `python` 버전이 3.11이 아님 | `.venv`를 지우고 3.11로 다시 만든다 |
| `cryptography package is required` | `pip install -r requirements.txt` 다시 실행 |
| MySQL 접속 거부 | `.env`의 `MYSQL_*` 값과 MySQL 서비스 실행 여부 확인 |
| 8501 포트 사용 중 | `streamlit run main.py --server.port 8502` |
| 한글 깨짐 | 파일 UTF-8 저장, DB `utf8mb4` 확인 |
