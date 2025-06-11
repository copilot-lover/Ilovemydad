from flask_cors import CORS
from flask import Flask, request, jsonify
import os
import json
import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled

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

    for vid in video_ids:
        transcripts[vid] = get_transcript(vid)

    return jsonify(transcripts)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
