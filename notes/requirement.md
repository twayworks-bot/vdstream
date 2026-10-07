# VDSTREAM 시스템 요구사항 정의서 (Requirement Specification)

- **문서 버전**: v1.0.0
- **최초 작성일**: 2026-10-06 22:42:16
- **문서 위치**: `notes/requirement.md`
- **관리 원칙**: 신규 요구사항 발생 시 기존 내용을 보존하고 누적(Cumulative) 기록함.

---

## 1. 개요 및 분석 배경

본 문서는 [GOAL.md](../GOAL.md)에 수립된 목적과 목표를 바탕으로, 비디오 업로드, 720p 트랜스코딩, 무다운로드 스트리밍, 동시성 제어, 보관 주기 관리 및 웹 대시보드 시스템을 실제 구축하기 위한 기능적/비기능적 개발 요구사항을 상세히 분해하고 명확히 정의한다.

---

## 2. 기능적 요구사항 (Functional Requirements - FR)

### FR-01: 비디오 업로드 및 입력 유효성 검사
- **FR-01-1**: 사용자는 웹 대시보드 및 외부 REST API(`multipart/form-data`)를 통해 비디오 파일을 업로드할 수 있어야 한다.
- **FR-01-2**: 지원 포맷은 일반 비디오 컨테이너(`.mp4`, `.mkv`, `.avi`, `.mov`, `.webm`, `.flv`)를 포함한다.
- **FR-01-3**: 업로드 시 고유한 비디오 식별자(UUIDv4 또는 타임스탬프 결합 해시)를 발급하여 파일명 충돌을 방지한다.
- **FR-01-4**: 업로드된 원본 비디오는 설정된 임시 저장소(`storage/uploads`)에 격리 저장된다.

### FR-02: 동영상 검증 및 길이/용량 제약 강제
- **FR-02-1**: FFprobe를 통해 영상의 재생 길이(Duration), 가로/세로 해상도, 비디오/오디오 코덱, 비트레이트를 추출한다.
- **FR-02-2**: 영상의 총 재생 길이가 **10분(600초)**을 초과하는 경우 트랜스코딩을 거부하고 상태를 `FAILED`로 변경하며, 상세 사유(예: `Exceeded max duration 600s`)를 기록한다.
- **FR-02-3**: 트랜스코딩 완료 후 최종 생성 파일 크기가 **100MB**를 초과할 경우 시스템 정책 위반으로 간주하고 실패 처리하거나 비트레이트 조정을 통해 100MB 이내로 맞춘다.

### FR-03: FFmpeg 기반 720p 트랜스코딩 파이프라인
- **FR-03-1**: 모든 입력 비디오는 최대 720p(높이 720픽셀 기준, 종횡비 자동 유지: `scale=-2:min(720\,ih)`)로 트랜스코딩한다. 원본이 720p 미만인 경우 불필요한 업스케일링을 방지하여 화질 저하를 막는다.
- **FR-03-2**: 표준 웹 호환성을 위해 비디오 코덱은 **H.264 (libx264)**, 오디오 코덱은 **AAC**로 인코딩한다.
- **FR-03-3**: 트랜스코딩 결과물은 2가지 형태로 생성한다:
  1. 단일 점진적 재생용 MP4 (`faststart` 플래그 적용)
  2. HLS(HTTP Live Streaming) 번들 (`.m3u8` 인덱스 파일 및 4초 단위 `.ts` 세그먼트 파일)
- **FR-03-4**: FFmpeg 바이너리가 호스트 시스템에 없을 경우를 대비하여 명확한 오류 로그와 관리자 알림을 제공하고, 개발/테스트 환경을 위한 모의(Mock/Fallback) 모드를 지원한다.

### FR-04: 동시성 제어 및 대기열(Queue) 관리 ($N < 5$)
- **FR-04-1**: 업로드 수락 및 트랜스코딩 동시 실행 작업 수는 환경변수 `MAX_CONCURRENT_TRANSCODE` ($N < 5$, 기본 3)에 의해 엄격히 제한된다.
- **FR-04-2**: 동시 허용치를 초과하는 작업은 메모리 내 작업 대기열(`asyncio.Queue`, 최대 용량 `MAX_QUEUE_SIZE=20`)에 인큐(Enqueue)된다.
- **FR-04-3**: 대기열 큐 크기마저 초과할 경우, API는 즉시 HTTP 429 (Too Many Requests) 또는 503 오류를 반환하여 서버 붕괴를 예방한다.
- **FR-04-4**: 작업 상태는 `QUEUED` -> `PROCESSING` -> `COMPLETED` / `FAILED` 단계로 실시간 갱신된다.

### FR-05: 동영상 스트리밍 및 동시 시청 제어 ($M = 5$)
- **FR-05-1**: 사용자는 다운로드 완료 없이 첫 청크부터 즉시 시청할 수 있는 스트리밍 엔드포인트를 제공받아야 한다.
- **FR-05-2**: HLS 스트리밍 엔드포인트(`/api/v1/videos/{video_id}/stream/hls/master.m3u8`) 및 MP4 Range 스트리밍 엔드포인트를 지원한다.
- **FR-05-3**: 전체 시스템의 동시 시청 스트림 수는 **최대 $M=5$개**로 제한된다.
- **FR-05-4**: 스트리밍 재생을 시작할 때 임시 세션 토큰(`session_id`)을 발급받아 슬롯을 점유하며, 플레이어의 주기적 하트비트(Heartbeat, 15~30초)가 끊기거나 재생이 종료되면 슬롯이 즉시 반환된다.
- **FR-05-5**: 가용 슬롯(5개)이 모두 소진되었을 때 스트림 재생을 요청하면 HTTP 429(Too Many Concurrent Streams) 응답을 반환하여 과도한 트래픽을 방어한다.
- **FR-05-6**: 스트리밍 라우터 우선순위 통제 (Route Collision Prevention): 고정 경로(`/master.m3u8`, `/mp4`)는 와일드카드 세그먼트 경로(`/{segment_name:path}`)보다 반드시 높은 우선순위로 매칭되어야 하며, `/mp4` 요청이 세그먼트 핸들러로 오인 라우팅되어 `Segment file not found` 오류가 발생하는 문제를 원천 방지한다.

### FR-06: 비디오 보관 수명주기(Retention Lifecycle) 관리
- **FR-06-1**: 모든 비디오는 업로드 시점을 기준으로 보관 만료일시(`expires_at = created_at + RETENTION_DAYS`)를 산출하여 DB에 저장한다 (기본 365일 / 1년).
- **FR-06-2**: 백그라운드 주기적 태스크(예: 매일 자정 또는 설정된 시간 간격)를 통해 `now > expires_at`인 비디오를 조회한다.
- **FR-06-3**: 만료된 비디오의 원본 파일, 트랜스코딩 MP4, HLS 세그먼트 디렉토리 및 DB 레코드를 안전하게 영구 삭제한다.
- **FR-06-4**: 대시보드 및 관리자 API를 통해 수동 즉시 삭제 및 만료 잔여 기간 조회를 지원한다.

### FR-07: 외부 연계용 RESTful API 제공
- **FR-07-1**: 다른 웹 애플리케이션에서 비디오 업로드, 상태 모니터링, 스트리밍 URL 획득을 프로그래밍 방식으로 수행할 수 있어야 한다.
- **FR-07-2**: 상세 API 사양은 `vdstream-api.md`에 정의된 규격을 정확히 준수한다.
- **FR-07-3**: 모든 API 응답은 표준 JSON 구조(`status`, `message`, `data`)를 준수한다.

### FR-08: 웹 관리 대시보드
- **FR-08-1**: HTML5/CSS/JavaScript 및 반응형 UI 기반으로 구현된다.
- **FR-08-2**: 주요 기능:
  1. 시스템 리소스 및 가용 슬롯 현황 (현재 대기 큐, 트랜스코딩 진행 수 $N/3$, 활성 스트리밍 수 $M/5$)
  2. 비디오 드래그 앤 드롭 파일 업로드 및 실시간 진행률 표시
  3. 비디오 목록 테이블 (파일명, 해상도, 길이, 용량, 상태, 등록일, 만료 예정일)
  4. 내장 비디오 플레이어 모달 (Hls.js 탑재, 무다운로드 즉시 스트리밍 시청)
  5. 영상 삭제 및 메타데이터 상세 보기 모달

### FR-09: 환경변수 기반 동적 Basepath 라우팅 (DEFAULT_PREFIX)
- **FR-09-1**: 전체 웹 서비스 및 API는 환경변수 `DEFAULT_PREFIX` (기본값: `vdstream`)를 루트 Basepath로 사용하여 마운트되어야 한다.
- **FR-09-2**: 웹 대시보드 진입점은 `http://<HOST>:<PORT>/{DEFAULT_PREFIX}/dashboard` 형태로 서비스되어야 한다.
- **FR-09-3**: REST API 진입점은 `http://<HOST>:<PORT>/{DEFAULT_PREFIX}/api/v1/*` 형태로 서비스되어야 한다.
- **FR-09-4**: `GET /` 및 `GET /{DEFAULT_PREFIX}` 호출 시 자동으로 `/{DEFAULT_PREFIX}/dashboard`로 리다이렉트되어야 한다.
- **FR-09-5**: 정적 자원(`/static`), Swagger 문서(`/docs`), OpenAPI 스펙(`/openapi.json`) 또한 `/{DEFAULT_PREFIX}` 하위에 정합성 있게 매핑되어야 한다.
- **FR-09-6**: `DEFAULT_PREFIX` 환경변수 값이 변경되더라도 소스 코드 수정 없이 모든 엔드포인트와 대시보드 링크, API 응답 URL이 동적으로 자동 반영되어야 한다.

### FR-10: Docker 컨테이너화 및 Persistent Volume, 헬스체크 지원
- **FR-10-1**: Linux 컨테이너 환경에서 FFmpeg 및 FFprobe 바이너리를 기본 제공하며, 환경변수 `FFMPEG_PATH=/usr/bin/ffmpeg` 및 `FFPROBE_PATH=/usr/bin/ffprobe`로 고정 지원한다.
- **FR-10-2**: 데이터베이스(SQLite) 및 미디어 스토리지(`storage/uploads`, `storage/transcoded`, `storage/hls`)의 영구 보존을 위해 `STORAGE_DIR=/app/storage` 및 `VOLUME ["/app/storage", "/app/downloads"]` 환경을 제공한다.
- **FR-10-3**: 기본 서비스 노출 포트를 5000(`EXPOSE 5000`)으로 구성한다.
- **FR-10-4**: 컨테이너 헬스체크 사양에 맞춰 `GET /{base_prefix}/api/status` 및 `GET /api/status` 엔드포인트를 제공하여 가동 상태를 검증한다.
- **FR-10-5**: 루트 진입점 모듈 `main:app`을 제공하여 `uvicorn` 및 `gunicorn` 기반 표준 컨테이너 구동 CMD를 지원한다.

### FR-11: FFmpeg 프로세스 스트림 인코딩 및 cp949 결함 방어
- **FR-11-1**: Windows 및 다국어 환경에서 FFmpeg/FFprobe 실행 시 시스템 기본 로케일(`cp949`) 디코딩으로 인한 `UnicodeDecodeError` 크래시를 방지하기 위해, 모든 `subprocess.run` 호출에 `encoding="utf-8"`, `errors="replace"`를 명시한다.
- **FR-11-2**: 인코딩 로그 내 저작권 기호(0xA9)나 다국어 비트 스트림이 포함되어 있어도 백그라운드 워커 스레드가 비정상 중단되지 않고 정상 트랜스코딩을 완료하도록 보장한다.

### FR-12: 트랜스코딩 실시간 진행률(0~100%) 추적 및 대시보드 상태 동기화
- **FR-12-1**: `Video` 모델 및 REST API 응답에 `progress_percent` (0.0 ~ 100.0) 필드를 기본 제공한다. (`QUEUED`: 0.0, `PROCESSING`: 1.0~99.0, `COMPLETED`: 100.0, `FAILED`: 0.0)
- **FR-12-2**: FFmpeg 트랜스코딩 실행 시 `-progress pipe:1`을 통해 실시간 `out_time_us`를 추출하고, 전체 재생 시간 대비 단조 증가(monotonic)하는 0~85%(MP4) -> 86~98%(HLS) -> 100%(완료) 진행률을 산출한다.
- **FR-12-3**: 인메모리 `progress_tracker`를 통해 밀리초 단위 실시간 진행률을 제공하여 API 폴링 시 즉각 응답한다.
- **FR-12-4**: 웹 대시보드 테이블에 진행률 프로그레스 바(%)를 실시간 렌더링하고, 트랜스코딩 완료 즉시 전체 페이지 새로고침 없이 녹색 [완료] 배지와 [재생] 및 [링크] 액션 버튼으로 매끄럽게 자동 전환한다.

---

## 3. 비기능적 요구사항 (Non-Functional Requirements - NFR)

### NFR-01: 성능 및 안정성
- 스트리밍 첫 청크 전달 지연 시간(Time To First Frame)은 로컬 환경 기준 1초 이내여야 한다.
- 백그라운드 워커의 비정상 종료(트랜스코딩 도중 에러 등) 시 상태를 즉시 `FAILED`로 기록하고 자원(세마포어 슬롯)을 누수 없이 회수해야 한다.

### NFR-02: 환경 설정 유연성 (.env)
- 모든 동시성 임계값($N, M$), 파일 크기 제한, 비디오 길이, 디렉토리 경로, FFmpeg 실행 경로 등은 `.env` 파일을 통해 코드 수정 없이 재설정 가능해야 한다.

### NFR-03: 보안 및 접근 제어
- 비디오 스트리밍 시 슬롯 토큰 검증을 통해 인가되지 않은 과도한 세션 증식을 억제한다.
- 파일명 위변조 방지(Path Traversal 공격 방어)를 위해 원본 파일명 대신 서버 내부 식별자를 물리적 파일명으로 매핑한다.

---

## 4. 변경 이력 (Changelog)

- **2026-10-06 22:42 (v1.0.0)**:
  - 사용자 요구사항을 기반으로 8대 기능적 요구사항(FR-01 ~ FR-08) 및 3대 비기능적 요구사항(NFR-01 ~ NFR-03) 최초 제정.
- **2026-10-06 23:14 (v1.0.1)**:
  - `/api/v1/streams/{video_id}/mp4` 호출 시 와일드카드 세그먼트 핸들러 오매칭으로 인한 `Segment file not found` 결함 보고 접수.
  - 스트리밍 엔드포인트 라우팅 우선순위 강제 규정 (FR-05-6) 누적 반영.
- **2026-10-06 23:37 (v1.0.2)**:
  - 웹 서비스 Basepath를 환경변수 `DEFAULT_PREFIX` (`vdstream`)로 동적 적용하는 요구사항 반영 (FR-09).
  - 대시보드(`/{DEFAULT_PREFIX}/dashboard`), API(`/{DEFAULT_PREFIX}/api/v1/*`), 문서(`/{DEFAULT_PREFIX}/docs`) 통합 라우팅 구조 정의.
- **2026-10-06 23:54 (v1.0.3)**:
  - Dockerfile 생성 및 FFmpeg 컨테이너 환경, Persistent Volume PATH 연동 요구사항 반영 (FR-10).
  - 헬스체크 사양 연동용 `/{base_prefix}/api/status` 엔드포인트 및 `main:app` 진입점 지원.
- **2026-10-07 00:08 (v1.0.4)**:
  - Windows 한국어 로케일 환경에서 FFmpeg 로그의 특수 바이트(`0xa9`) 디코딩 중 `UnicodeDecodeError: 'cp949'` 크래시 결함 수정 (FR-11).
  - `encoding="utf-8"`, `errors="replace"` 표준 적용.
- **2026-10-07 00:30 (v1.0.5)**:
  - 트랜스코딩 진행중 정체 결함 해결, 0~100% 진행률 실시간 추적기(`ProgressTracker`) 및 API/대시보드 프로그레스 바 연동 (FR-12).


