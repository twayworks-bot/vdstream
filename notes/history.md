# VDSTREAM 개발 이력 (history.md)

## [2026-10-06 22:42] v1.0.0 요구사항 접수 및 설계/구현/테스트 완료

### 1. 사용자 요구사항 접수 요약
- 비디오 업로드 후 최대 720p 트랜스코딩 및 저장.
- 저장된 영상을 관리하는 웹 대시보드 구현.
- 다른 웹앱에서 업로드, 트랜스코딩 상태, 스트리밍 URL을 연동할 수 있는 REST API 제공.
- 다운로드 없는 즉시 스트리밍(HLS 및 Range) 기능 제공.
- FFmpeg 기반 트랜스코딩 & 기본 365일(설정 기반) 보관 관리.
- 동시 업로드 및 트랜스코딩 수 $N < 5$ (기본 3) 제어 및 초과 시 큐 방식 지원.
- 최대 동시 스트리밍 수 $M = 5$ 지원 (초과 시 제어).
- 트랜스코딩 영상 제약: 최대 100MB, 재생 길이 10분(600초) 이내 강제.
- `.env`에 정의된 FFMPEG 관련 환경값을 점검하고 추가 필요한 환경값 저장 및 출력.
- 문서 체계 준수:
  - `vdstream-api.md`: 외부 참조용 API Spec 작성.
  - `README.md`: 프로젝트 목적, 사용법, 구현 기능 상세 기술.
  - `GOAL.md`: 목적과 목표 수립 및 구현 내역 요약.
  - `notes/requirement.md`: 기능적/비기능적 요구사항 상세 정의 및 누적 관리.
  - `notes/SPECIFICATION.md`: 기술 스펙, 패키지 구성도, 기능 세부 설명, 제약사항, 제안 내용.
  - `notes/plan_202610062242.md`: MVP 정의 및 세부 개발 계획.
  - `notes/req_202610062242.md`: 사용자 원본 요구사항 및 계획 기록.
  - `notes/result_202610062242.md`: 산출물 생성 및 검증 기록.

### 2. 진행 및 구현 완료 내역
- [x] 사용자 원본 요구사항 분석 및 `notes/req_202610062242.md` 생성.
- [x] `.env` 환경 변수 분석 및 세부 트랜스코딩, 스트리밍, 보관 경로 파라미터 누적 보강 완료.
- [x] 프로젝트 목표 및 구현 요약 `GOAL.md` 작성.
- [x] 시스템 요구사항 정의서 `notes/requirement.md` 작성.
- [x] 기술 사양서 `notes/SPECIFICATION.md` 작성.
- [x] MVP 정의 및 개발 일정 계획 `notes/plan_202610062242.md` 작성.
- [x] 외부 연동용 상세 REST API 명세서 `vdstream-api.md` 작성.
- [x] 종합 프로젝트 가이드 및 매뉴얼 `README.md` 작성.
- [x] 시스템 백엔드 코어 모듈 구현:
  - `app/config.py`: 환경변수 관리 및 자동 디렉토리 생성
  - `app/database.py` & `app/models/video.py`: SQLite SQLAlchemy 메타데이터 모델
  - `app/services/ffmpeg_service.py`: 720p 트랜스코딩, HLS 분할 생성, 10분/100MB 유효성 검사, fallback 안내 지원
  - `app/services/queue_manager.py`: $N=3$ 세마포어, FIFO 대기열(`asyncio.Queue`), 자동 복구 워커 풀
  - `app/services/stream_manager.py`: $M=5$ 동시 스트리밍 슬롯 제어, 세션 하트비트, 타임아웃 자동 회수
  - `app/services/retention_service.py`: 365일 보관 만료 검사 및 미디어/DB 영구 삭제
  - `app/api/v1/`: 업로드, 상태 폴링, 스트리밍 URL 발급, 시스템 현황, HLS/MP4 Range 스트리밍 서빙 엔드포인트
- [x] 모던 웹 대시보드 UI 구현:
  - `app/templates/base.html`, `app/templates/index.html` (Bootstrap 5, Icons, Hls.js)
  - `app/static/css/style.css`, `app/static/js/dashboard.js` (드래그앤드롭 업로드, 실시간 상태 폴링, HLS 무다운로드 즉시 스트리밍 플레이어)
  - `run.py` & `app/main.py`: 서버 구동 엔트리포인트 및 라이프사이클 관리
- [x] 자동화 테스트 작성 및 100% 통과 (`tests/`):
  - API, 큐 오버플로우 방어, 동시 스트리밍 $M=5$ 슬롯 제한, 10분/100MB 제약조건 검증 (총 9개 테스트 통과)
- [x] 라이브 서버 기동 및 엔드포인트 정상 응답 검증 완료 (HTTP 200 OK)
- [x] 산출물 및 최종 보고서 `notes/result_202610062242.md` 작성 완료.

---

## [2026-10-06 23:14] v1.0.1 MP4 스트리밍 라우팅 충돌 결함 해결 및 실제 FFmpeg 트랜스코딩 연동

### 1. 결함 보고 내용
- 사용자 영상(`5마을.찬양제.mp4`) 트랜스코딩 완료 후 `GET /api/v1/streams/{video_id}/mp4` 호출 시 `{"detail":"Segment file not found."}` 404 오류 발생.

### 2. 원인 분석 및 해결 조치
1. **와일드카드 라우트 섀도잉(Route Shadowing) 수정**:
   - `app/api/v1/streams.py`에서 `/{video_id}/{segment_name:path}`가 `/{video_id}/mp4`보다 위에 위치하여 `segment_name="mp4"`로 오인식되던 순서 결함 수정.
   - `/{video_id}/mp4` 핸들러를 상단으로 재배치하고, 세그먼트 핸들러에 `segment_name == "mp4"` 방어 로직 추가.
2. **실제 FFmpeg 7.1 바이너리 탑재 및 ffprobe 부재 대응**:
   - `./bin/ffmpeg.exe` 바이너리 배치.
   - ffprobe가 없더라도 `ffmpeg -i` 출력의 표준 에러 스트림을 정규식으로 파싱하여 비디오 메타데이터(Duration, Resolution, Codec, Bitrate)를 온전히 추출하도록 `app/services/ffmpeg_service.py` 개선.
3. **사용자 영상 실제 720p 트랜스코딩 완료**:
   - `vid_20261006230843_66bae763`: 1280x720, 91.21MB (<= 100MB), 8분 5초 (<= 10분), HLS 세그먼트 및 MP4 정상 생성.
4. **검증**:
   - 단위 테스트 10개 100% 통과 (`tests/test_stream_limit.py`에 MP4 라우트 방어 테스트 추가).
   - 라이브 서버에서 `GET .../mp4` Range 206 Partial Content 및 `GET .../master.m3u8` 200 OK 동작 확인.
   - 산출물 기록: `notes/req_202610062314.md`, `notes/result_202610062314.md`.

---

## [2026-10-06 23:37] v1.0.2 웹 서비스 Basepath 및 Subpath 동적 라우팅 (`DEFAULT_PREFIX`) 구축

### 1. 사용자 요구사항
- 웹 시작 Basepath는 환경변수 `DEFAULT_PREFIX` (기본값: `vdstream`)로 지정되어야 함.
- 진입점: `http://localhost:5000/{DEFAULT_PREFIX}/dashboard` 및 `http://localhost:5000/{DEFAULT_PREFIX}/api/v1/*`.
- 환경변수 `DEFAULT_PREFIX` 값 변경 시 소스 수정 없이 유연하게 동적 적용.

### 2. 진행 및 구현 완료 내역
- [x] 사용자 원본 요구사항 분석 및 `notes/req_202610062337.md` 작성.
- [x] 누적 요구사항 정의서 `notes/requirement.md`에 `FR-09` 추가 및 변경 이력 갱신.
- [x] 기술 사양서 `notes/SPECIFICATION.md`에 섹션 2.1 Basepath / Subpath URL 계층도 추가.
- [x] `app/config.py`: `base_prefix` 동적 정규화 프로퍼티 구현.
- [x] `app/main.py`:
  - `docs_url`, `redoc_url`, `openapi_url`을 `{base_prefix}/docs` 등으로 마운트.
  - 정적 자산 마운트: `{base_prefix}/static`.
  - 서브라우터 마운트: `{base_prefix}/api/v1` 및 `{base_prefix}/dashboard`.
  - 루트(`/`) 및 `/{DEFAULT_PREFIX}` 호출 시 `{base_prefix}/dashboard`로 307 자동 리다이렉트.
- [x] `app/api/v1/videos.py`: 반환 URL (`status_url`, `hls_master_url`, `mp4_range_url` 등)에 `base_prefix` 적용.
- [x] `app/dashboard/routes.py`, `app/templates/base.html`, `app/static/js/dashboard.js`:
  - 템플릿 context에 `base_prefix` 주입.
  - `<meta name="base-prefix">` 태그 제공.
  - 대시보드 JS의 모든 XHR/fetch 호출 및 링크에 `BASE_PREFIX` 동적 결합.
- [x] `run.py`, `README.md`, `vdstream-api.md`: 동적 Basepath 기반 접속 주소 및 API 명세 동기화.
- [x] 자동화 테스트 (`tests/`):
  - 루트 및 프리픽스 리다이렉트 검증 테스트 추가 (`test_root_and_prefix_redirects`).
  - 총 11개 단위/통합 테스트 100% 통과 (11 Passed, 0 Failed).
- [x] 라이브 서버 구동 검증:
  - `/` -> `/vdstream/dashboard` 리다이렉트 확인.
  - `/vdstream/dashboard` 200 OK.
  - `/vdstream/api/v1/system/status` 200 OK.
  - `/vdstream/api/v1/streams/{video_id}/mp4` 206 Partial Content.
  - `/vdstream/docs` Swagger UI 200 OK.
- [x] 산출물 및 최종 보고서 `notes/result_202610062337.md` 작성.

---

## [2026-10-06 23:54] v1.0.3 Dockerfile 컨테이너화, Persistent Volume 연동 및 헬스체크 지원

### 1. 사용자 요구사항
- Docker container 생성을 위한 `Dockerfile` 작성.
- Database 파일에 대한 persistent volume 연동 PATH 환경값 설정.
- 노출 포트 5000번 (`EXPOSE 5000`) 설정.
- 컨테이너의 `DEFAULT_PREFIX` 환경세팅 값에 맞춰 앱의 기본 base URL 작동.
- 컨테이너 헬스체크 정의:
  ```dockerfile
  HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=5s \
      CMD python -c "import os, requests; prefix = os.getenv('DEFAULT_PREFIX', ''); requests.get(f'http://localhost:5000{prefix}/api/status')"
  ```
- 시작 CMD 규격 반영:
  - Uvicorn (기본): `CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5000"]`
  - Gunicorn (대안): `CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", ... "main:app"]`
- `.env`의 필수 환경변수 반영, Linux base container 내 FFmpeg/FFprobe 실행 바이너리 연동 및 경로 고정.
- `README.md` 업데이트.

### 2. 진행 및 구현 완료 내역
- [x] 사용자 원본 요구사항 분석 및 `notes/req_202610062354.md` 작성.
- [x] 누적 요구사항 정의서 `notes/requirement.md`에 `FR-10` 및 v1.0.3 변경 이력 반영.
- [x] `requirements.txt`: 컨테이너 헬스체크용 `requests` 및 운영 서버용 `gunicorn` 추가.
- [x] `app/main.py`: 동적 prefix 지원 헬스체크 엔드포인트 `GET /{base_prefix}/api/status` 및 `GET /api/status` 구현.
- [x] `main.py`: 루트 진입점 모듈 생성 (`from app.main import app`)으로 `main:app` 참조 완벽 지원.
- [x] `Dockerfile`:
  - `python:3.11-slim` 기반
  - `ffmpeg`, `curl` 패키지 설치
  - `FFMPEG_PATH=/usr/bin/ffmpeg`, `FFPROBE_PATH=/usr/bin/ffprobe` 고정
  - `STORAGE_DIR=/app/storage`, `DOWNLOAD_DIR=/app/downloads`, `DB_URL=sqlite:////app/storage/vdstream.db` 영구 볼륨 경로 환경변수
  - `DEFAULT_PREFIX=/vdstream`
  - `EXPOSE 5000`
  - `VOLUME ["/app/storage", "/app/downloads"]`
  - 사용자 지정 `HEALTHCHECK` 지시문 완벽 탑재
  - `CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5000"]` 적용
- [x] `.dockerignore`: 빌드 컨텍스트 최적화 (가상환경, 테스트 캐시, 로컬 바이너리 제외).
- [x] `README.md` & `vdstream-api.md`: Docker 빌드/실행 가이드 및 헬스체크 엔드포인트 명세 반영.
- [x] 자동화 테스트 (`tests/`):
  - 컨테이너 헬스체크 검증 테스트 추가 (`test_container_healthcheck_api`).
  - 총 12개 테스트 100% 통과 (`12 passed in 2.44s`).
- [x] 산출물 및 최종 보고서 `notes/result_202610062354.md` 작성.

---

## [2026-10-07 00:08] v1.0.4 Windows subprocess cp949 디코딩 결함 (`UnicodeDecodeError`) 긴급 수정

### 1. 사용자 오류 보고
- 비디오 업로드 후 트랜스코딩 시 `subprocess.py`의 `_readerthread` 스레드에서 `UnicodeDecodeError: 'cp949' codec can't decode byte 0xa9 in position 1682: illegal multibyte sequence` 예외 발생.

### 2. 원인 분석 및 해결 조치
1. **원인 분석**:
   - Windows 한국어 로케일 환경에서 `subprocess.run(..., text=True)` 호출 시 인코딩 파라미터가 없으면 시스템 기본 인코딩(`cp949`)으로 stdout/stderr 파이프를 읽음.
   - FFmpeg 실행 및 x264 인코딩 시 저작권 기호(`©`, 0xA9)나 다국어 비트스트림 로그가 출력되면서 `cp949` 디코딩 실패 발생.
2. **해결 조치**:
   - `app/services/ffmpeg_service.py` 내의 모든 `subprocess.run` 호출(메타데이터 추출 `probe_video`, 720p MP4 인코딩, HLS 분할 인코딩)에 `encoding="utf-8"`, `errors="replace"` 명시.
   - 비표준 바이트나 다국어 메타데이터가 들어오더라도 안전하게 디코딩되도록 방어.
3. **검증**:
   - 단위 테스트 작성 (`tests/test_ffmpeg_encoding.py`) 및 전체 14개 테스트 100% 통과 (`14 passed in 2.58s`).
   - 실제 사용자 업로드 파일(`vid_20261007000649_cbbab149`, 원본 171MB / 길이 7분 26초)에 대한 `probe_video` 및 트랜스코딩 결과 파일(92.44MB <= 100MB) 정상 연동 확인.
- [x] 산출물 및 최종 보고서 `notes/result_202610070008.md` 작성.

---

## [2026-10-07 00:30] v1.0.5 트랜스코딩 진행중 정체 결함 해결 및 0~100% 진행률 실시간 API/대시보드 지원

### 1. 사용자 요구사항
- 업로드 후 transcoding 완료 상태가 모니터링되지 않아 진행중 표시가 계속 뜨는 상태로 유지되는 현상 해결.
- 완료 상태까지 정상 진행되고, 이 때 프로그레스 상태값(진행률 %, 0~100%)을 출력할 수 있도록 수정.
- API로 진행상태값을 100%까지 추정/제공할 수 있도록 구현 검토 및 반영.

### 2. 원인 분석 및 해결 조치
1. **원인 분석**:
   - `dashboard.js`의 폴링 조건이 `active_transcoding_count > 0 || queued_count > 0`일 때만 비디오 목록을 갱신하도록 되어 있어, 트랜스코딩이 방금 완료되어 카운트가 0이 되면 폴링이 중단되어 화면이 '변환 중...'에 멈추는 결함 존재.
   - `Video` 모델 및 REST API에 진행률(%) 필드가 존재하지 않아 실시간 진행률 추정 불가.
2. **해결 조치**:
   - `app/models/video.py`: `progress_percent` (Float, 0.0~100.0) 컬럼 및 `to_dict()` 필드 추가.
   - `app/database.py`: SQLite 자동 컬럼 마이그레이션 (`ALTER TABLE`) 추가.
   - `app/services/progress_tracker.py`: 인메모리 스레드 안전 진행률 관리자 싱글톤 신규 구현 (단조 증가 및 클램핑 보장).
   - `app/services/ffmpeg_service.py`: `transcode_to_720p_and_hls`에 `progress_callback` 연동, FFmpeg `-progress pipe:1`의 실시간 `out_time_us`를 파싱하여 0% -> 85%(MP4) -> 86~98%(HLS) -> 100%(완료) 진행률 산출.
   - `app/services/queue_manager.py`: 백그라운드 워커에 실시간 콜백 및 단계별 DB/메모리 진행률 동기화 연동.
   - `app/api/v1/videos.py`: `GET /status` 및 `GET /videos` 목록 API에 실시간 `progress_percent` 노출.
   - `app/templates/index.html` & `app/static/js/dashboard.js`:
     - 테이블 '진행 상태' 열에 프로그레스 바 및 % 텍스트 추가.
     - 1.5초 주기 무중단 라이브 폴링 및 DOM 실시간 갱신 적용.
     - 완료 시 전체 새로고침 없이 녹색 [완료 (스트리밍 가능)] 배지와 [재생], [링크] 버튼으로 즉시 자동 전환.
   - `vdstream-api.md`: `progress_percent` 필드 및 응답 명세 반영.
3. **검증**:
   - 신규 단위/통합 테스트 작성 (`tests/test_progress.py`).
   - 전체 18개 테스트 100% 통과 (`18 passed in 3.61s`).
- [x] 산출물 및 최종 보고서 `notes/result_202610070030.md` 작성.



