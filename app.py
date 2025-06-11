from flask_cors import CORS
from flask import Flask, request, jsonify, send_file
import os
import json
import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled
import io
import zipfile

app = Flask(__name__)
CORS(app, resources={r"/transcripts": {"origins": "https://studio.botpress.cloud"}})

def get_video_ids_from_playlist(playlist_url):
    ydl_opts = {'quiet': True, 'extract_flat': True, 'force_generic_extractor': True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(playlist_url, download=False)
        return [entry['id'] for entry in info_dict['entries'] if 'id' in entry]

def get_transcript(video_id):
    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id)
        return "\n".join([entry['text'] for entry in transcript])
    except TranscriptsDisabled:
        return "[No transcript available]"
    except Exception as e:
        return f"Error fetching transcript: {str(e)}"

@app.route('/transcripts', methods=['POST'])
def process_playlist():
    data = request.get_json()
    playlist_url = data.get("playlist_url")
    if not playlist_url:
        return jsonify({"error": "Missing playlist_url"}), 400

    video_ids = get_video_ids_from_playlist(playlist_url)
    transcripts = {}

    # Save each transcript to a separate file
    saved_files = []
    for vid in video_ids:
        transcript = get_transcript(vid)
        transcripts[vid] = transcript
        filename = f"{vid}_transcript.txt"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(transcript)
        saved_files.append(filename)

    # Return transcripts and list of generated files (for download)
    return jsonify({"transcripts": transcripts, "files": saved_files})

@app.route('/download-zip', methods=['POST'])
def download_zip():
    # Get list of filenames to include in the ZIP from the request
    files_to_zip = request.json.get('files', [])

    # Create an in-memory ZIP file
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w') as zf:
        for filename in files_to_zip:
            # Only add file if it exists
            if os.path.exists(filename):
                zf.write(filename)
    zip_buffer.seek(0)

    # Return the ZIP as a downloadable response
    return send_file(
        zip_buffer,
        as_attachment=True,
        download_name='playlist_files.zip',
        mimetype='application/zip'
    )

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
