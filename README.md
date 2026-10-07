# VDSTREAM (Video Transcoding & Instant Streaming Platform)

> **비디오 업로드, 720p 자동 트랜스코딩, 무다운로드 HLS 즉시 스트리밍, 동시성 큐 제어($N<5$, $M=5$), 1년 보관 수명주기를 완벽하게 제공하는 마이크로서비스 플랫폼**

[![Python Version](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![FFmpeg](https://img.shields.io/badge/FFmpeg-720p%20HLS-green.svg)](https://ffmpeg.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](#)

---

## 1. 프로젝트 목적 (Purpose)

**VDSTREAM**은 사용자가 비디오 영상을 업로드하면 표준 720p 해상도로 자동 트랜스코딩하고, 클라이언트가 영상을 다운로드받지 않고도 브라우저나 외부 앱에서 즉시 재생할 수 있는 HLS 및 Range 스트리밍 환경을 제공합니다. 

특히 제한된 서버 컴퓨팅 파워와 네트워크 대역폭을 보호하기 위해:
- **트랜스코딩 동시 작업 수 $N < 5$ (기본 3개)** 엄격 제한 및 FIFO 대기열 지원
- **동시 스트리밍 접속 수 $M = 5$개** 슬롯 제한 및 하트비트 세션 관리
- 트랜스코딩 결과물 **최대 100MB 이하, 재생 길이 10분(600초) 이하** 강제 정책
- 업로드된 동영상의 **기본 365일 (1년)** 자동 보관 및 만료 수명주기 관리

를 시스템 레벨에서 보장하며, 자체 **웹 대시보드**와 외부 웹 애플리케이션 연동을 위한 **REST API**를 동시에 제공합니다.

---

## 2. 주요 기능 및 특징 (Key Features)

### 2.1 최대 720p 고효율 트랜스코딩 파이프라인
- 업로드된 다양한 형식(MP4, MKV, MOV, AVI, WEBM 등)의 비디오를 웹 표준 H.264(libx264) 및 AAC 오디오로 자동 인코딩.
- 원본 해상도가 720p를 초과할 경우 비율을 유지하며 720p로 자동 다운스케일링(`scale=-2:min(720\,ih)`), 720p 미만은 원본 크기 유지.
- 결과물 크기가 **100MB**를 절대 초과하지 않도록 영상 길이에 따른 동적 비트레이트 제어 적용.
- 재생 길이가 **10분(600초)**을 초과하는 영상은 업로드/트랜스코딩 단계에서 사전 차단.

### 2.2 무다운로드 즉시 스트리밍 (Instant Streaming)
- 비디오 파일 전체 다운로드 완료를 기다리지 않고 첫 청크부터 즉시 버퍼링 없이 감상.
- **HLS (HTTP Live Streaming)**: 4초 단위 `.ts` 세그먼트 및 `.m3u8` 플레이리스트 생성으로 모바일/웹 완벽 호환.
- **HTTP Range (206 Partial Content)**: MP4 바이트 레인지 시크(Seek) 스트리밍 지원.

### 2.3 엄격한 동시성 제어 및 리소스 보호
- **업로드 & 트랜스코딩 세마포어 ($N < 5$, 기본 3)**:
  - 동시 인코딩 수를 제한하여 CPU/GPU 과부하 방지.
  - 초과 요청은 비동기 작업 대기열(`asyncio.Queue`, 최대 20개)에서 순차 대기.
  - 대기 큐 초과 시 `429 Too Many Requests`로 서버 안정성 보장.
- **동시 스트리밍 슬롯 풀 ($M = 5$)**:
  - 최대 5개의 활성 시청 세션만 동시 스트리밍 허용.
  - 브라우저 플레이어의 하트비트(15초 주기)를 통해 30초 이상 무응답 세션 자동 회수.
  - 5개 초과 시 `429 Too Many Streams` 반환.

### 2.4 보관 수명주기 (Retention Lifecycle) 자동화
- 영상 업로드 시 보관 만료일시(`expires_at = created_at + RETENTION_DAYS`)를 자동 기록 (기본값: 365일 / 1년).
- 백그라운드 스케줄러가 만료된 동영상의 원본, 트랜스코딩 MP4, HLS 세그먼트 디렉토리 및 메타데이터를 자동 영구 삭제.

### 2.5 모던 반응형 웹 대시보드
- 드래그 앤 드롭 파일 업로드 및 실시간 진행 상태 모니터링.
- 현재 대기 큐, 트랜스코딩 실행 현황, 활성 스트리밍 슬롯 현황을 한눈에 파악.
- 내장 **Hls.js** 비디오 플레이어 모달을 통해 즉시 스트리밍 시청.
- 비디오 메타데이터 확인, 즉시 다운로드 및 수동 삭제 기능 지원.

### 2.6 외부 연동 RESTful API (`vdstream-api.md`)
- 다른 웹앱이나 모바일 앱에서 업로드, 진행 상태 폴링, 타겟 스트리밍 주소 획득, 비디오 삭제를 원격 제어할 수 있는 표준 REST 엔드포인트 제공.

---

## 3. 시스템 아키텍처 및 디렉토리 구조

```text
vdstream/
├── .env                              # 환경설정 파일 (FFmpeg 경로, 동시성, 제약조건 등)
├── GOAL.md                           # 프로젝트 목표 및 구현 요약
├── README.md                         # 본 프로젝트 문서
├── vdstream-api.md                   # 외부 연동용 REST API 명세서
├── run.py                            # 서버 실행 진입점
├── requirements.txt                  # 파이썬 의존성 패키지
├── app/
│   ├── main.py                       # FastAPI 애플리케이션 진입점 및 생명주기
│   ├── config.py                     # .env 설정 로더
│   ├── database.py                   # SQLite DB 연결 및 세션 관리
│   ├── models/
│   │   └── video.py                  # 비디오 메타데이터 및 상태 ORM 모델
│   ├── services/
│   │   ├── ffmpeg_service.py         # FFmpeg/FFprobe 비디오 변환 및 10분/100MB 검증
│   │   ├── queue_manager.py          # N=3 트랜스코딩 큐 및 작업 워커
│   │   ├── stream_manager.py         # M=5 동시 스트리밍 세션 슬롯 관리자
│   │   └── retention_service.py      # 365일 보관 수명주기 만료 관리자
│   ├── api/v1/
│   │   ├── videos.py                 # 업로드, 상태, 스트림 URL 발급 API
│   │   └── streams.py                # HLS m3u8/ts 및 Range 스트리밍 서빙 엔드포인트
│   ├── dashboard/
│   │   └── routes.py                 # 대시보드 SSR 웹 라우트
│   ├── templates/
│   │   ├── base.html                 # 기본 레이아웃 (Bootstrap & CDN)
│   │   └── index.html                # 대시보드 메인 화면
│   └── static/
│       ├── css/style.css             # 모던 UI 스타일
│       └── js/dashboard.js           # 대시보드 비동기 UI 인터랙션
├── storage/                          # 비디오 데이터 저장소
│   ├── uploads/                      # 원본 비디오 저장소
│   ├── transcoded/                   # 720p 변환 MP4 저장소
│   └── hls/                          # HLS 세그먼트 저장소
└── notes/                            # 엔지니어링 기록 및 사양서
```

---

## 4. 환경 변수 설정 (`.env`)

시스템은 루트 디렉토리의 `.env` 파일을 통해 모든 정책을 설정할 수 있습니다.

| 환경 변수 | 기본값 | 설명 |
|---|---|---|
| `HOST` | `0.0.0.0` | 서버 바인딩 호스트 |
| `PORT` | `5000` | 서버 서비스 포트 |
| `APP_PIN` | `1234` | 기본 관리자 인증 핀 번호 |
| `MAX_CONCURRENT_TRANSCODE` | `3` | 동시 트랜스코딩 작업 수 ($N < 5$) |
| `MAX_QUEUE_SIZE` | `20` | 최대 트랜스코딩 대기열 크기 |
| `MAX_CONCURRENT_STREAMS` | `5` | 최대 동시 스트리밍 시청 수 ($M = 5$) |
| `STREAM_SESSION_TIMEOUT_SECONDS` | `30` | 스트리밍 하트비트 만료 시간 (초) |
| `MAX_OUTPUT_VIDEO_SIZE_MB` | `100` | 트랜스코딩 결과물 최대 허용 용량 (MB) |
| `MAX_VIDEO_DURATION_SECONDS` | `600` | 비디오 최대 허용 재생 시간 (10분 = 600초) |
| `TARGET_MAX_HEIGHT` | `720` | 최대 트랜스코딩 해상도 (720p) |
| `RETENTION_DAYS` | `365` | 비디오 기본 보관 기간 (일 단위) |
| `FFMPEG_PATH` | `./bin/ffmpeg.exe` | FFmpeg 실행 바이너리 경로 (또는 시스템 PATH) |
| `FFPROBE_PATH` | `./bin/ffprobe.exe` | FFprobe 실행 바이너리 경로 (또는 시스템 PATH) |
| `STORAGE_DIR` | `./storage` | 미디어 및 DB 통합 저장 루트 디렉토리 |

---

## 5. 설치 및 실행 방법 (Quick Start)

### 5.1 사전 준비 사항
- Python 3.10 이상
- FFmpeg 및 FFprobe 바이너리:
  - 시스템 PATH에 등록되어 있거나, 본 프로젝트 루트의 `./bin/ffmpeg.exe` 및 `./bin/ffprobe.exe` 위치에 복사합니다.
  - *(참고: FFmpeg가 설치되지 않은 개발 환경에서도 시스템 자체 진단 및 안내 모드를 통해 안전하게 구동됩니다.)*

### 5.2 의존성 설치
```bash
pip install -r requirements.txt
```

### 5.3 서버 실행
```bash
python run.py
```
서버가 기동되면 환경변수 `DEFAULT_PREFIX` (기본값 `vdstream`)에 따라 다음 URL로 서비스됩니다:
- **웹 대시보드**: [http://localhost:5000/vdstream/dashboard](http://localhost:5000/vdstream/dashboard) (루트 `http://localhost:5000/` 접속 시 자동 리다이렉트)
- **REST API 문서 (Swagger)**: [http://localhost:5000/vdstream/docs](http://localhost:5000/vdstream/docs)
- **REST API 엔드포인트**: `http://localhost:5000/vdstream/api/v1/*`
- **API Spec 문서**: [`vdstream-api.md`](vdstream-api.md)

---

## 6. 외부 애플리케이션 연동 가이드

외부 웹 애플리케이션에서 VDSTREAM을 비디오 처리 백엔드로 활용하려면 다음 3단계 API를 호출합니다:

1. **비디오 업로드**:
   `POST /vdstream/api/v1/videos/upload` 로 비디오 파일 전송 -> `video_id` 수신
2. **상태 폴링**:
   `GET /vdstream/api/v1/videos/{video_id}/status` 를 1~2초 주기로 확인하여 `COMPLETED` 여부 체크
3. **스트리밍 재생 URL 획득**:
   `GET /vdstream/api/v1/videos/{video_id}/stream` 호출 -> `hls_master_url` 및 `session_id` 획득 후 웹 플레이어에 전달

상세한 요청/응답 페이로드 및 cURL / Python 예제는 [vdstream-api.md](vdstream-api.md)를 참조하십시오.

---

## 7. Docker 컨테이너 배포 가이드 (Containerization)

VDSTREAM은 FFmpeg 및 Python 구동 환경이 모두 포함된 공식 Dockerfile을 제공합니다.

### 7.1 Dockerfile 주요 사양
- **Base Image**: `python:3.11-slim` (안정적이고 경량화된 Linux Debian 환경)
- **FFmpeg/FFprobe**: Linux OS 패키지로 자동 설치 및 고정 (`/usr/bin/ffmpeg`, `/usr/bin/ffprobe`)
- **기본 노출 포트**: `5000` (`EXPOSE 5000`)
- **동적 Prefix 지원**: `DEFAULT_PREFIX` 환경변수 (`/vdstream`, 미지정 시 `/` 동작 지원)
- **지속성 볼륨 (Persistent Volumes)**:
  - Database 파일 및 변환 비디오: `/app/storage` (`DB_URL=sqlite:////app/storage/vdstream.db`, `STORAGE_DIR=/app/storage`)
  - 다운로드 디렉토리: `/app/downloads` (`DOWNLOAD_DIR=/app/downloads`)
- **컨테이너 헬스체크 (HEALTHCHECK)**:
  ```dockerfile
  HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=5s \
      CMD python -c "import os, requests; prefix = os.getenv('DEFAULT_PREFIX', ''); requests.get(f'http://localhost:5000{prefix}/api/status')"
  ```
- **기본 기동 커맨드**:
  - Uvicorn (기본): `CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5000"]`
  - Gunicorn 운영 모드: `CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "-k", "uvicorn.workers.UvicornWorker", "--log-level", "debug", "--access-logfile", "-", "--error-logfile", "-", "--capture-output", "main:app"]`

### 7.2 Docker 이미지 빌드
```bash
docker build -t vdstream:latest .
```

### 7.3 Docker 컨테이너 실행 (Persistent Volume 마운트)
호스트 머신의 디렉토리(`./storage`)를 컨테이너 볼륨(`/app/storage`)에 마운트하여 데이터베이스와 비디오 파일이 영구 보존되도록 실행합니다:

```bash
docker run -d \
  --name vdstream-server \
  -p 5000:5000 \
  -e DEFAULT_PREFIX=/vdstream \
  -e MAX_CONCURRENT_TRANSCODE=3 \
  -e MAX_CONCURRENT_STREAMS=5 \
  -v $(pwd)/storage:/app/storage \
  -v $(pwd)/downloads:/app/downloads \
  vdstream:latest
```

### 7.4 컨테이너 상태 및 헬스체크 확인
```bash
docker ps
# STATUS 열에 "(healthy)" 표시 확인
docker inspect --format='{{json .State.Health}}' vdstream-server
```

---

## 8. 자동화 테스트 실행

단위 기능 및 동시성 큐/스트리밍 슬롯 제한, 컨테이너 헬스체크 API를 검증하려면 pytest를 실행합니다:

```bash
pytest -v
```

