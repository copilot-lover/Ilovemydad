import os
import uuid
import threading
import tempfile
import zipfile
from queue import Queue
from flask import Flask, request, jsonify, send_file, Response
from flask_cors import CORS
import yt_dlp
from pytube import Playlist
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled

app = Flask(__name__)
CORS(app)

# In-memory job store: job_id → Queue of SSE messages + zip_path attr
jobs = {}

def get_video_ids_from_playlist(playlist_url):
    # Primary method: yt_dlp
    try:
        opts = {'quiet': True, 'extract_flat': True}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(playlist_url, download=False)
            ids = [e['id'] for e in info.get('entries', []) if 'id' in e]
        if ids:
            return ids
    except Exception:
        pass

    # Fallback: pytube
    try:
        pl = Playlist(playlist_url)
        return [video.video_id for video in pl.videos]
    except Exception:
        return []

def get_transcript(video_id):
    try:
        trs = YouTubeTranscriptApi.get_transcript(video_id)
        return "\n".join([x['text'] for x in trs])
    except TranscriptsDisabled:
        return "[No transcript available]"
    except Exception as e:
        return f"[Error fetching transcript: {e}]"

def sse_event(progress, message):
    # Server-Sent Event format
    return f"data: {{\"progress\": {progress}, \"message\": \"{message}\"}}\n\n"

def background_job(job_id, playlist_url):
    q = jobs[job_id]
    q.put(sse_event(0, "Job started"))
    ids = get_video_ids_from_playlist(playlist_url)
    total = len(ids)
    if total == 0:
        q.put(sse_event(100, "No videos found"))
        q.put(None)
        return

    q.put(sse_event(5, f"Found {total} videos"))
    tempdir = tempfile.mkdtemp()
    zip_path = os.path.join(tempdir, f"{job_id}.zip")

    with zipfile.ZipFile(zip_path, 'w') as zf:
        for idx, vid in enumerate(ids, start=1):
            pct = 5 + idx * 90 // total
            q.put(sse_event(pct, f"Processing {idx}/{total}"))
            text = get_transcript(vid)
            zf.writestr(f"{vid}.txt", text)

    q.put(sse_event(100, "Complete"))
    jobs[job_id].zip_path = zip_path
    q.put(None)  # end of stream

@app.route("/transcripts", methods=["POST"])
def start_transcripts():
    data = request.get_json() or {}
    url = data.get("playlist_url")
    if not url:
        return jsonify(error="Missing playlist_url"), 400

    job_id = uuid.uuid4().hex
    jobs[job_id] = Queue()
    thread = threading.Thread(target=background_job, args=(job_id, url), daemon=True)
    thread.start()
    return jsonify(job_id=job_id), 202

@app.route("/status/<job_id>")
def status(job_id):
    q = jobs.get(job_id)
    if not q:
        return jsonify(error="Invalid job_id"), 404

    def stream():
        while True:
            evt = q.get()
            if evt is None:
                break
            yield evt

    return Response(stream(), mimetype="text/event-stream")

@app.route("/download/<job_id>")
def download(job_id):
    job = jobs.get(job_id)
    if not job or not hasattr(job, "zip_path"):
        return jsonify(error="Not ready"), 404
    return send_file(job.zip_path, mimetype="application/zip", as_attachment=True, download_name="transcripts.zip")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
