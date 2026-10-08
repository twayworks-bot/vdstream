let activeHls = null;
let currentSessionId = null;
let heartbeatInterval = null;
let statusPollingInterval = null;

// Read base_prefix dynamically from HTML meta tag
const BASE_PREFIX = document.querySelector('meta[name="base-prefix"]')?.getAttribute('content') || '';

document.addEventListener('DOMContentLoaded', () => {
    initDropzone();
    initUploadForm();
    startStatusPolling();
});

// Dropzone Drag & Drop Setup
function initDropzone() {
    const dropzone = document.getElementById('dropzone');
    const fileInput = document.getElementById('video-file');
    const fileInfo = document.getElementById('selected-file-info');
    const submitBtn = document.getElementById('btn-upload-submit');

    if (!dropzone || !fileInput) return;

    ['dragenter', 'dragover'].forEach(eventName => {
        dropzone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropzone.classList.add('drag-over');
        });
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropzone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropzone.classList.remove('drag-over');
        });
    });

    dropzone.addEventListener('drop', (e) => {
        const files = e.dataTransfer.files;
        if (files && files.length > 0) {
            fileInput.files = files;
            updateSelectedFileInfo(files[0]);
        }
    });

    fileInput.addEventListener('change', () => {
        if (fileInput.files && fileInput.files.length > 0) {
            updateSelectedFileInfo(fileInput.files[0]);
        }
    });

    function updateSelectedFileInfo(file) {
        const sizeMb = (file.size / (1024 * 1024)).toFixed(2);
        fileInfo.innerHTML = `<i class="bi bi-file-earmark-check me-1"></i>선택된 파일: <strong>${file.name}</strong> (${sizeMb} MB)`;
        fileInfo.classList.remove('d-none');
        submitBtn.disabled = false;
    }
}

// Upload Form with Progress
function initUploadForm() {
    const form = document.getElementById('upload-form');
    const fileInput = document.getElementById('video-file');
    const titleInput = document.getElementById('video-title');
    const submitBtn = document.getElementById('btn-upload-submit');
    const progressContainer = document.getElementById('upload-progress-container');
    const progressBar = document.getElementById('upload-progress-bar');
    const percentText = document.getElementById('upload-percent-text');
    const statusText = document.getElementById('upload-status-text');

    if (!form) return;

    form.addEventListener('submit', (e) => {
        e.preventDefault();
        const file = fileInput.files[0];
        if (!file) {
            alert('업로드할 비디오 파일을 선택해 주세요.');
            return;
        }

        const formData = new FormData();
        formData.append('file', file);
        if (titleInput.value.trim()) {
            formData.append('title', titleInput.value.trim());
        }

        submitBtn.disabled = true;
        progressContainer.classList.remove('d-none');
        progressBar.style.width = '0%';
        percentText.innerText = '0%';
        statusText.innerText = '서버로 파일 업로드 중...';

        const xhr = new XMLHttpRequest();
        xhr.open('POST', `${BASE_PREFIX}/api/v1/videos/upload`, true);

        xhr.upload.onprogress = (event) => {
            if (event.lengthComputable) {
                const percent = Math.round((event.loaded / event.total) * 100);
                progressBar.style.width = percent + '%';
                percentText.innerText = percent + '%';
            }
        };

        xhr.onload = () => {
            if (xhr.status === 202) {
                statusText.innerText = '업로드 완료! 트랜스코딩 대기열에 등록되었습니다.';
                progressBar.classList.remove('bg-primary');
                progressBar.classList.add('bg-success');
                setTimeout(() => {
                    location.reload();
                }, 1000);
            } else {
                let errorMsg = '업로드 실패';
                try {
                    const res = JSON.parse(xhr.responseText);
                    errorMsg = res.detail || errorMsg;
                } catch (err) {}
                alert('업로드 오류: ' + errorMsg);
                submitBtn.disabled = false;
                progressContainer.classList.add('d-none');
            }
        };

        xhr.onerror = () => {
            alert('네트워크 오류로 업로드에 실패했습니다.');
            submitBtn.disabled = false;
            progressContainer.classList.add('d-none');
        };

        xhr.send(formData);
    });
}

// Instant Streaming Playback
async function playVideo(videoId, title) {
    const playerModal = new bootstrap.Modal(document.getElementById('playerModal'));
    const videoTitleElem = document.getElementById('player-video-title');
    const sessionBadge = document.getElementById('stream-session-badge');
    const sessionIdText = document.getElementById('stream-session-id-text');
    const video = document.getElementById('video-player');
    const loadingOverlay = document.getElementById('player-loading-overlay');

    videoTitleElem.innerText = title;
    loadingOverlay.classList.remove('d-none');
    playerModal.show();

    // Clean up previous session if any
    closePlayer(false);

    try {
        const resp = await fetch(`${BASE_PREFIX}/api/v1/videos/${videoId}/stream`);
        if (resp.status === 429) {
            const err = await resp.json();
            alert(`동시 스트리밍 시청 한도 초과 (최대 5명): ${err.detail}`);
            playerModal.hide();
            return;
        }
        if (!resp.ok) {
            const err = await resp.json();
            alert(`스트리밍 오류: ${err.detail || '스트림을 시작할 수 없습니다.'}`);
            playerModal.hide();
            return;
        }

        const data = (await resp.json()).data;
        currentSessionId = data.session_id;
        sessionIdText.innerText = currentSessionId;
        sessionBadge.innerText = '스트리밍 연결됨 (슬롯 확보)';
        sessionBadge.className = 'badge bg-success-subtle text-success border border-success-subtle';

        const hlsUrl = data.streaming_urls.hls_master_url;

        // Start heartbeat every 15 seconds
        heartbeatInterval = setInterval(() => {
            if (currentSessionId) {
                fetch(`${BASE_PREFIX}/api/v1/streams/${currentSessionId}/heartbeat`, { method: 'POST' })
                    .catch(e => console.warn('Heartbeat error:', e));
            }
        }, 15000);

        // Load stream using Hls.js or Native Video
        if (Hls.isSupported()) {
            activeHls = new Hls({
                enableWorker: true,
                lowLatencyMode: true,
            });
            activeHls.loadSource(hlsUrl);
            activeHls.attachMedia(video);
            activeHls.on(Hls.Events.MANIFEST_PARSED, () => {
                loadingOverlay.classList.add('d-none');
                video.play().catch(e => console.log('Autoplay prevented:', e));
            });
            activeHls.on(Hls.Events.ERROR, (event, errData) => {
                if (errData.fatal) {
                    console.error('Fatal HLS error:', errData);
                    // Fallback to MP4 Range stream
                    console.log('Falling back to MP4 range stream...');
                    video.src = data.streaming_urls.mp4_range_url;
                    loadingOverlay.classList.add('d-none');
                    video.play();
                }
            });
        } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
            // Native Safari/iOS support
            video.src = hlsUrl;
            loadingOverlay.classList.add('d-none');
            video.play();
        } else {
            // Direct MP4 Range fallback
            video.src = data.streaming_urls.mp4_range_url;
            loadingOverlay.classList.add('d-none');
            video.play();
        }

    } catch (err) {
        console.error('Failed to initiate stream:', err);
        alert('스트리밍 요청 중 네트워크 오류가 발생했습니다.');
        playerModal.hide();
    }
}

// Close player and release stream session
function closePlayer(hideModal = true) {
    const video = document.getElementById('video-player');
    if (video) {
        video.pause();
        video.removeAttribute('src');
        video.load();
    }

    if (activeHls) {
        activeHls.destroy();
        activeHls = null;
    }

    if (heartbeatInterval) {
        clearInterval(heartbeatInterval);
        heartbeatInterval = null;
    }

    if (currentSessionId) {
        const sidToRelease = currentSessionId;
        currentSessionId = null;
        fetch(`${BASE_PREFIX}/api/v1/streams/${sidToRelease}/release`, { method: 'POST' })
            .catch(e => console.warn('Release slot error:', e));
    }
}

// Show API details modal
function showVideoDetails(videoId) {
    const detailsModal = new bootstrap.Modal(document.getElementById('detailsModal'));
    const origin = window.location.origin;
    const previewInput = document.getElementById('modal-preview-url');
    if (previewInput) {
        previewInput.value = `${origin}${BASE_PREFIX}/api/v1/streams/${videoId}/preview`;
    }
    document.getElementById('modal-hls-url').value = `${origin}${BASE_PREFIX}/api/v1/streams/${videoId}/master.m3u8`;
    document.getElementById('modal-mp4-url').value = `${origin}${BASE_PREFIX}/api/v1/streams/${videoId}/mp4`;
    document.getElementById('modal-status-url').value = `${origin}${BASE_PREFIX}/api/v1/videos/${videoId}/status`;
    detailsModal.show();
}

function copyToClipboard(elementId) {
    const input = document.getElementById(elementId);
    input.select();
    navigator.clipboard.writeText(input.value).then(() => {
        alert('클립보드에 복사되었습니다: ' + input.value);
    });
}

// Delete video
async function deleteVideo(videoId) {
    if (!confirm('정말로 이 동영상을 삭제하시겠습니까? 트랜스코딩된 파일과 HLS 세그먼트가 영구 삭제됩니다.')) {
        return;
    }

    try {
        const resp = await fetch(`${BASE_PREFIX}/api/v1/videos/${videoId}`, { method: 'DELETE' });
        if (resp.ok) {
            const row = document.getElementById(`video-row-${videoId}`);
            if (row) row.remove();
            alert('동영상이 삭제되었습니다.');
            location.reload();
        } else {
            const err = await resp.json();
            alert('삭제 실패: ' + (err.detail || '오류 발생'));
        }
    } catch (e) {
        alert('네트워크 오류로 삭제하지 못했습니다.');
    }
}

// Periodic status polling to auto-update resource counters and pending videos
function startStatusPolling() {
    statusPollingInterval = setInterval(async () => {
        try {
            const resp = await fetch(`${BASE_PREFIX}/api/v1/system/status`);
            if (resp.ok) {
                const info = (await resp.json()).data;
                const trans = info.transcoding;
                const stream = info.streaming;

                const elTrans = document.getElementById('stat-active-transcode');
                const elQueue = document.getElementById('stat-queued-count');
                const elStream = document.getElementById('stat-active-streams');
                const barTrans = document.getElementById('bar-transcode');
                const barQueue = document.getElementById('bar-queue');
                const barStream = document.getElementById('bar-stream');

                if (elTrans) elTrans.innerText = `${trans.active_transcoding_count} / ${trans.max_concurrent_transcode}`;
                if (elQueue) elQueue.innerText = `${trans.queued_count} / ${trans.max_queue_size}`;
                if (elStream) elStream.innerText = `${stream.active_stream_sessions} / ${stream.max_concurrent_streams}`;

                if (barTrans) barTrans.style.width = `${(trans.active_transcoding_count / trans.max_concurrent_transcode) * 100}%`;
                if (barQueue) barQueue.style.width = `${(trans.queued_count / trans.max_queue_size) * 100}%`;
                if (barStream) barStream.style.width = `${(stream.active_stream_sessions / stream.max_concurrent_streams) * 100}%`;

                // Check if any row in the table is still pending or if system has active tasks
                const hasPendingRows = document.querySelector('.video-status-cell .spinner-border, .video-status-cell .bi-hourglass-split') !== null;
                if (hasPendingRows || trans.active_transcoding_count > 0 || trans.queued_count > 0) {
                    await checkAndRefreshPendingVideos();
                }
            }
        } catch (e) {
            // ignore background poll errors
        }
    }, 1500);
}

async function checkAndRefreshPendingVideos() {
    try {
        const resp = await fetch(`${BASE_PREFIX}/api/v1/videos?limit=20`);
        if (!resp.ok) return;

        const data = (await resp.json()).data;
        const items = data.items || [];

        for (const item of items) {
            const row = document.getElementById(`video-row-${item.video_id}`);
            if (!row) continue;

            const cells = row.querySelectorAll('td');
            if (cells.length < 7) continue;

            const durationCell = cells[2];
            const sizeCell = cells[3];
            const statusCell = cells[4];
            const actionCell = cells[6];

            const pct = Math.round(item.progress_percent || 0);

            if (item.status === 'PROCESSING') {
                statusCell.innerHTML = `
                    <div class="status-badge-wrap mb-1">
                        <span class="badge bg-primary-subtle text-primary border border-primary-subtle" title="${item.status_message || ''}">
                            <span class="spinner-border spinner-border-sm me-1"></span>변환 중 (<span class="progress-val">${pct}%</span>)
                        </span>
                    </div>
                    <div class="progress" style="height: 6px; width: 140px;">
                        <div class="progress-bar progress-bar-striped progress-bar-animated bg-primary" role="progressbar" style="width: ${pct}%;"></div>
                    </div>
                `;
            } else if (item.status === 'QUEUED') {
                statusCell.innerHTML = `
                    <div class="status-badge-wrap mb-1">
                        <span class="badge bg-warning-subtle text-warning border border-warning-subtle">
                            <i class="bi bi-hourglass-split me-1"></i>대기 큐 (0%)
                        </span>
                    </div>
                    <div class="progress" style="height: 6px; width: 140px;">
                        <div class="progress-bar bg-warning" role="progressbar" style="width: 5%;"></div>
                    </div>
                `;
            } else if (item.status === 'COMPLETED') {
                const hasPlayBtn = actionCell.querySelector('.btn-success') !== null;
                if (!hasPlayBtn) {
                    // Update Status Cell to Completed badge
                    statusCell.innerHTML = `
                        <span class="badge bg-success-subtle text-success border border-success-subtle">
                            <i class="bi bi-check-circle-fill me-1"></i>완료 (스트리밍 가능)
                        </span>
                    `;

                    // Update Duration & Resolution
                    durationCell.innerHTML = `
                        <div><i class="bi bi-clock me-1 text-secondary"></i>${item.duration_formatted}</div>
                        <div class="text-secondary small">${item.width ? `${item.width}x${item.height}` : '-'}</div>
                    `;

                    // Update File Size
                    sizeCell.innerHTML = item.file_size_mb > 0
                        ? `<span class="badge bg-secondary-subtle text-secondary-emphasis border">${item.file_size_mb} MB</span>`
                        : `<span class="text-secondary small">-</span>`;

                    // Update Actions to Play & Details buttons
                    const safeTitle = (item.title || '').replace(/'/g, "\\'");
                    actionCell.innerHTML = `
                        <div class="btn-group btn-group-sm">
                            <button class="btn btn-success" onclick="playVideo('${item.video_id}', '${safeTitle}');" title="즉시 스트리밍 시청">
                                <i class="bi bi-play-fill me-1"></i>재생
                            </button>
                            <button class="btn btn-outline-info" onclick="showVideoDetails('${item.video_id}');" title="API 정보 및 스트림 링크">
                                <i class="bi bi-link-45deg"></i>
                            </button>
                            <button class="btn btn-outline-danger" onclick="deleteVideo('${item.video_id}');" title="삭제">
                                <i class="bi bi-trash"></i>
                            </button>
                        </div>
                    `;
                }
            } else if (item.status === 'FAILED') {
                statusCell.innerHTML = `
                    <span class="badge bg-danger-subtle text-danger border border-danger-subtle" title="${item.status_message || ''}">
                        <i class="bi bi-x-circle-fill me-1"></i>실패
                    </span>
                `;
            }
        }
    } catch (e) {
        console.warn('Live pending video check error:', e);
    }
}
