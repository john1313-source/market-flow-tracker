# 한국 주식시장 수급 트래커

외국인·기관·개인의 코스피 현물 수급과 코스피200 선물 베이시스를 매 영업일 누적하고, GitHub Pages 대시보드와 텔레그램 일일 리포트로 보여주는 프로젝트입니다. 매매 주문 기능은 포함하지 않습니다.

## 수집 항목

- `pykrx`: 코스피 투자자별 순매수 대금 상세 분류, 코스피200 지수, SK하이닉스·삼성전자 외국인 순매수
- KRX 정보데이터시스템: 코스피200 선물 최근월물 종가, 외국인·기관 선물 순매수 거래대금, 미결제약정
- Npay 증권 모바일: KRX OTP 또는 CSV 다운로드 실패 시 최신 선물 종가·투자자 수급 폴백
- 계산값: 실제·이론 베이시스, 괴리율, 분기 둘째 목요일 만기, 외국인 현물·선물 20일 누적

현물·선물 순매수 데이터는 CSV에 원 단위로 저장하고, 대시보드와 텔레그램에서 억/조 단위로 표시합니다. `금융투자`와 `외국인`은 서로 다른 열로 끝까지 보존하며 합산하지 않습니다.

## 파일 구조

```text
.
├─ .github/workflows/daily-update.yml  # 평일 KST 16:30 자동 실행
├─ data/flows.csv                      # 원본 일별 데이터
├─ docs/                               # GitHub Pages 정적 대시보드
├─ market_tracker/                     # 수집·계산·저장·텔레그램 모듈
├─ scripts/update_flows.py             # 당일 수집
├─ scripts/backfill.py                 # 과거 백필
├─ scripts/send_telegram.py            # 텔레그램 전송
├─ config.yaml                         # 금리·배당수익률·대시보드 주소
└─ requirements.txt
```

`data/flows.csv`는 같은 날짜를 다시 수집하면 기존 행을 덮어씁니다. 저장할 때 날짜순 정렬, 중복 제거, 전체 20일 누적값 재계산을 수행하고 `docs/data/flows.csv`도 자동으로 동기화합니다.

## 1. 로컬 설정 및 백필

Python 3.11 환경에서 먼저 KRX 계정 환경변수를 설정한 뒤 실행합니다.

```powershell
# Windows PowerShell
$env:KRX_ID = "내_ID"
$env:KRX_PW = "내_비밀번호"
```

```bash
python -m venv .venv
source .venv/bin/activate        # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
python scripts/backfill.py --start 2026-05-01
```

KRX 파생 과거 데이터가 특정 날짜에 제공되지 않아도 pykrx 현물 백필은 계속 진행되며 해당 행의 파생 출처가 `unavailable`로 남습니다. 현물만 빠르게 백필하려면 다음 옵션을 사용합니다.

```bash
python scripts/backfill.py --start 2026-05-01 --skip-derivatives
```

일일 수집과 메시지 미리보기는 다음과 같습니다.

```bash
python scripts/update_flows.py --date 2026-07-20
python scripts/send_telegram.py --dry-run
```

`config.yaml`의 `market.cd_rate`와 `market.dividend_yield`는 소수로 수동 관리합니다. 예를 들어 2.65%는 `0.0265`입니다. 텔레그램 링크용 `telegram.dashboard_url`도 실제 Pages 주소로 바꾸세요.

## 2. GitHub Secrets와 Variables 등록

저장소의 **Settings → Secrets and variables → Actions**에서 아래 값을 등록합니다.

### Secrets

- `KRX_ID`: KRX 정보데이터시스템 로그인 ID
- `KRX_PW`: KRX 정보데이터시스템 로그인 비밀번호
- `BOT_TOKEN`: BotFather가 발급한 텔레그램 봇 토큰
- `CHAT_ID`: 메시지를 받을 개인 또는 채널의 chat ID

### Variables

- `DASHBOARD_URL`: 예) `https://my-id.github.io/market-flow/`

`DASHBOARD_URL` Variable을 생략하면 `config.yaml` 값이 사용됩니다. 봇이 채널에 보내는 경우 먼저 봇을 채널 관리자로 추가해야 합니다.

2026년 현재 KRX 정보데이터시스템은 로그인 세션을 요구합니다. `pykrx==1.2.8`도 `KRX_ID`, `KRX_PW` 환경변수로 로그인합니다. 값이 없거나 로그인에 실패하면 빈 결과를 휴장일로 잘못 처리하지 않고 수집을 실패시킵니다.

## 3. GitHub Pages 활성화

1. 저장소의 **Settings → Pages**로 이동합니다.
2. **Build and deployment → Source**를 `Deploy from a branch`로 선택합니다.
3. Branch는 `main`, 폴더는 `/docs`를 선택하고 저장합니다.
4. 표시된 공개 URL을 `DASHBOARD_URL` Variable과 `config.yaml`에 반영합니다.

## 4. 자동화 동작

`daily-update.yml`은 월~금 UTC 07:30, 즉 KST 16:30에 실행됩니다. **Actions → 일일 수급 업데이트 → Run workflow**에서 수동 실행도 가능합니다.

실행 순서는 다음과 같습니다.

1. 장 마감 데이터 수집 및 CSV 멱등 갱신
2. 변경된 원본·Pages CSV 커밋 및 푸시
3. 텔레그램 일일 리포트 전송

휴장일처럼 pykrx 결과가 비어 있으면 성공으로 종료하고 커밋이나 텔레그램 전송을 하지 않습니다. 수집·계산·저장 오류는 예외를 삼키지 않으므로 워크플로가 실패합니다. 텔레그램 단계만 `continue-on-error`로 분리되어 전송 장애가 데이터 커밋을 되돌리지 않습니다.

## KRX OTP와 폴백

KRX 수집기는 pykrx의 인증 쿠키 세션을 공유하고, 화면별 Referer를 포함해 `generate.cmd`로 OTP를 발급받은 뒤 `download_csv/download.cmd`에 POST합니다. KRX 화면 개편에 대비해 `config.yaml`의 BLD 후보를 순서대로 시도합니다. OTP가 `LOGOUT`/오류 HTML을 반환하거나 CSV를 해석할 수 없으면 네이버 선물 페이지로 폴백하며 다음 열에 기록합니다.

- `derivative_source`: `krx`, `naver`, `unavailable`
- `fallback_used`: `true` 또는 `false`

Npay 증권 모바일 폴백은 최신 최근월물 종가와 외국인·기관 수급을 제공하지만 미결제약정과 과거 일자 수급은 제공하지 않습니다. 따라서 폴백 행의 `open_interest`는 빈 값일 수 있고, 과거 파생 백필은 `unavailable`로 남을 수 있습니다. Npay 증권까지 실패하면 일일 수집은 실패 처리되어 잘못된 행을 저장하지 않습니다.

## 테스트

```bash
python -m pytest -q
```

테스트는 분기 둘째 목요일 만기 계산, 베이시스 뱃지, 20일 누적, 같은 날짜 덮어쓰기, 텔레그램 방향 전환 문구를 확인합니다.
