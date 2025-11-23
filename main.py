# ===== RENDER/GITHUB SERVER COMPONENT =====
# Deploy this on render.com or similar service

from flask import Flask, request, jsonify, send_file
import yt_dlp
import requests
import os
import tempfile
import time
import re

app = Flask(__name__)

# Configuration
TRENDING_SONGS_API = "https://www.googleapis.com/youtube/v3/videos"
YOUTUBE_API_KEY = os.environ.get('YOUTUBE_API_KEY')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')            # Set this in your environment
GEMINI_MODEL = os.environ.get('GEMINI_MODEL', 'gemini-1.0')  # Adjust if you have a different model name
TEMP_DIR = tempfile.gettempdir()

# Track last processing error for clearer responses
LAST_PROCESS_ERROR = None

def get_trending_video_using_gemini(max_results=5, region_code='US'):
    """Fetch top music videos from YouTube and use Gemini (Google Generative AI) to pick the
    single most trending video.
    """
    if not YOUTUBE_API_KEY:
        print("YOUTUBE_API_KEY not set, cannot fetch trending videos")
        return None

    params = {
        'part': 'snippet,statistics',
        'chart': 'mostPopular',
        'videoCategoryId': '10',  # Music
        'maxResults': max_results,
        'regionCode': region_code,
        'key': YOUTUBE_API_KEY
    }

    try:
        resp = requests.get(TRENDING_SONGS_API, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        items = data.get('items', [])

        candidates = []
        for i, it in enumerate(items):
            vid = it.get('id')
            snippet = it.get('snippet', {}) or {} 
            stats = it.get('statistics', {}) or {}
            title = snippet.get('title', '<no title>')
            channel = snippet.get('channelTitle', '<no channel>')
            try:
                views = int(stats.get('viewCount', 0)) if stats.get('viewCount') is not None else 0
            except Exception:
                views = 0
            url = f"https://www.youtube.com/watch?v={vid}"
            candidates.append({
                'index': i + 1,
                'id': vid,
                'title': title,
                'channel': channel,
                'views': views,
                'url': url
            })

        if not candidates:
            return None

        # If Gemini API key available, ask Gemini to choose the best candidate index
        if GEMINI_API_KEY:
            try:
                # Build a concise prompt for Gemini
                lines = [f"{c['index']}. Title: {c['title']} | Channel: {c['channel']} | Views: {c['views']}" for c in candidates]
                prompt = (
                    "You are given a short list of YouTube music videos with title, channel and view count.\n"
                    "Pick the single most trending video right now and respond only with the candidate index number (e.g. 1).\n"
                    "If multiple are equally trending pick the one with the highest view count.\n\nCandidates:\n" + "\n".join(lines)
                )

                # Generative Language API endpoint (adjust model name if necessary)
                url = f"https://generativelanguage.googleapis.com/v1/models/{GEMINI_MODEL}:generateText"
                headers = {
                    'Authorization': f"Bearer {GEMINI_API_KEY}",
                    'Content-Type': 'application/json'
                }
                body = {
                    'prompt': {
                        'text': prompt
                    },
                    'temperature': 0.0,
                    'maxOutputTokens': 32
                }

                gresp = requests.post(url, headers=headers, json=body, timeout=15)
                gresp.raise_for_status()
                jr = gresp.json()

                # Extract text robustly
                text = ''
                if isinstance(jr, dict):
                    if jr.get('candidates') and len(jr['candidates']) > 0:
                        cand = jr['candidates'][0]
                        if isinstance(cand, dict):
                            text = cand.get('content', '') or cand.get('output', '') or str(cand)
                    if not text and jr.get('output'):
                        if isinstance(jr['output'], list) and len(jr['output']) > 0:
                            parts = []
                            for o in jr['output']:
                                if isinstance(o, dict):
                                    parts.append(o.get('content', '') or o.get('text', '') or '')
                                else:
                                    parts.append(str(o))
                            text = "\n".join([p for p in parts if p])
                    if not text and jr.get('results'):
                        r0 = jr['results'][0]
                        if isinstance(r0, dict) and r0.get('output'):
                            parts = []
                            for o in r0.get('output'):
                                if isinstance(o, dict):
                                    parts.append(o.get('content', '') or '')
                            text = '\n'.join([p for p in parts if p])
                if not text and isinstance(jr.get('text'), str):
                    text = jr.get('text')

                m = re.search(r"(\d+)", text or "")
                if m:
                    idx = int(m.group(1))
                    for c in candidates:
                        if c['index'] == idx:
                            return c['url']

            except Exception as e:
                print(f"Gemini selection failed: {e}")

        best = max(candidates, key=lambda x: x.get('views', 0))
        return best['url']

    except Exception as e:
        print(f"Error fetching trending videos: {e}")
        return None


def get_trending_song():
    """Get latest trending song from YouTube Music.

    This function prefers a Gemini-based selection when GEMINI_API_KEY is set.
    """
    try:
        gem_choice = get_trending_video_using_gemini(max_results=5)
        if gem_choice:
            return gem_choice
    except Exception as e:
        print(f"Gemini trending selection error: {e}")

    try:
        if not YOUTUBE_API_KEY:
            return "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

        params = {
            'part': 'snippet',
            'chart': 'mostPopular',
            'videoCategoryId': '10',  # Music category
            'maxResults': 1,
            'regionCode': 'US',
            'key': YOUTUBE_API_KEY
        }

        response = requests.get(TRENDING_SONGS_API, params=params, timeout=10)
        data = response.json()

        if data.get('items'):
            video_id = data['items'][0]['id']
            return f"https://www.youtube.com/watch?v={video_id}"
    except Exception as e:
        print(f"Error getting trending song: {e}")

    return "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def download_youtube_audio(url, output_path):
    """Download audio from YouTube video"""
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': output_path,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'quiet': True,
        'no_warnings': True
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return output_path + '.mp3'
    except Exception as e:
        print(f"Error downloading audio: {e}")
        return None


def download_youtube_video(url, output_path):
    """Download video from YouTube"""
    ydl_opts = {
        'format': 'best[ext=mp4]',
        'outtmpl': output_path,
        'quiet': True,
        'no_warnings': True
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return output_path
    except Exception as e:
        print(f"Error downloading video: {e}")
        return None


def process_video(input_video_path, output_video_path):
    """Remove original audio and add trending song"""
    global LAST_PROCESS_ERROR
    try:
        # Lazy import moviepy to avoid startup crash if not installed
        try:
            from moviepy.editor import VideoFileClip, AudioFileClip, CompositeAudioClip
        except Exception as e:
            LAST_PROCESS_ERROR = f"moviepy import failed: {e}"
            print(LAST_PROCESS_ERROR)
            return False

        video = VideoFileClip(input_video_path)

        trending_song_url = get_trending_song()
        print(f"Using trending song: {trending_song_url}")

        audio_path = os.path.join(TEMP_DIR, f'trending_song_{int(time.time())}')
        downloaded_audio = download_youtube_audio(trending_song_url, audio_path)

        if not downloaded_audio or not os.path.exists(downloaded_audio):
            print("Failed to download trending song, using silent video")
            video_without_audio = video.without_audio()
            video_without_audio.write_videofile(
                output_video_path,
                codec='libx264',
                audio_codec='aac',
                temp_audiofile=os.path.join(TEMP_DIR, 'temp_audio.m4a'),
                remove_temp=True
            )
        else:
            new_audio = AudioFileClip(downloaded_audio)

            if video.duration > new_audio.duration:
                loops_needed = int(video.duration / new_audio.duration) + 1
                new_audio = CompositeAudioClip([
                    new_audio.set_start(i * new_audio.duration) 
                    for i in range(loops_needed)
                ])

            new_audio = new_audio.subclip(0, video.duration)

            video_without_audio = video.without_audio()
            final_video = video_without_audio.set_audio(new_audio)

            final_video.write_videofile(
                output_video_path,
                codec='libx264',
                audio_codec='aac',
                temp_audiofile=os.path.join(TEMP_DIR, 'temp_audio.m4a'),
                remove_temp=True
            )

            new_audio.close()
            final_video.close()

            if os.path.exists(downloaded_audio):
                os.remove(downloaded_audio)

        video_without_audio.close()
        video.close()

        return True

    except Exception as e:
        LAST_PROCESS_ERROR = str(e)
        print(f"Error processing video: {e}")
        return False

@app.route('/download', methods=['POST'])
def download_video():
    data = request.json
    video_url = data.get('videoUrl')

    if not video_url:
        return jsonify({'error': 'No video URL provided'}), 400

    try:
        output_path = os.path.join(TEMP_DIR, f'video_{int(time.time())}.mp4')
        downloaded_path = download_youtube_video(video_url, output_path)

        if downloaded_path and os.path.exists(downloaded_path):
            return jsonify({
                'success': True,
                'fileUrl': f'/get-file/{os.path.basename(downloaded_path)}'
            })
        else:
            return jsonify({'error': 'Failed to download video'}), 500

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/process-video', methods=['POST'])
def process_video_endpoint():
    data = request.json
    video_url = data.get('videoUrl')

    if not video_url:
        return jsonify({'error': 'No video URL provided'}), 400

    try:
        input_path = os.path.join(TEMP_DIR, f'input_{int(time.time())}.mp4')
        response = requests.get(video_url, stream=True)

        with open(input_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        output_path = os.path.join(TEMP_DIR, f'output_{int(time.time())}.mp4')
        success = process_video(input_path, output_path)

        if success and os.path.exists(output_path):
            return jsonify({
                'success': True,
                'processedFileUrl': f'/get-file/{os.path.basename(output_path)}'
            })
        else:
            err = LAST_PROCESS_ERROR or 'Failed to process video'
            return jsonify({'error': err}), 500

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if os.path.exists(input_path):
            os.remove(input_path)

@app.route('/get-file/<filename>', methods=['GET'])
def get_file(filename):
    file_path = os.path.join(TEMP_DIR, filename)
    if os.path.exists(file_path):
        return send_file(file_path, mimetype='video/mp4')
    return jsonify({'error': 'File not found'}), 404

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
