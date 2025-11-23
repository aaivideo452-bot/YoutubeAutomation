from flask import Flask, request, jsonify, send_file
import requests
import os
import tempfile
import time
import json

app = Flask(__name__)

# Configuration
YOUTUBE_API_KEY = os.environ.get('YOUTUBE_API_KEY', '')
TEMP_DIR = tempfile.gettempdir()

print(f"=== SERVER STARTING ===")
print(f"TEMP_DIR: {TEMP_DIR}")


def download_youtube_video_via_api(url, output_path):
    """
    Download video using cobalt.tools API (no YouTube blocks!)
    Alternative to yt-dlp that bypasses restrictions
    """
    print(f"\n>>> Downloading via API: {url}")
    
    try:
        # Use cobalt.tools API (free, no auth needed)
        api_url = "https://api.cobalt.tools/api/json"
        
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
        
        payload = {
            "url": url,
            "vQuality": "720",  # Download 720p quality
            "filenamePattern": "basic",
            "isAudioOnly": False
        }
        
        print(">>> Requesting download link from API...")
        response = requests.post(api_url, json=payload, headers=headers, timeout=30)
        
        if response.status_code != 200:
            print(f">>> API error: {response.status_code}")
            print(f">>> Response: {response.text}")
            return None
        
        data = response.json()
        print(f">>> API response: {data.get('status', 'unknown')}")
        
        # Handle different response types
        download_url = None
        
        if data.get('status') == 'redirect' or data.get('status') == 'stream':
            download_url = data.get('url')
        elif data.get('status') == 'picker':
            # Multiple formats available, pick first video
            picker = data.get('picker', [])
            if picker:
                download_url = picker[0].get('url')
        
        if not download_url:
            print(f">>> No download URL found. Response: {data}")
            # Fallback to yt-dlp if API fails
            return download_youtube_video_ytdlp(url, output_path)
        
        # Download the video
        print(f">>> Downloading from: {download_url[:50]}...")
        video_response = requests.get(download_url, stream=True, timeout=300)
        video_response.raise_for_status()
        
        final_path = output_path if output_path.endswith('.mp4') else output_path + '.mp4'
        
        with open(final_path, 'wb') as f:
            for chunk in video_response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        if os.path.exists(final_path):
            size = os.path.getsize(final_path)
            print(f">>> SUCCESS! Downloaded: {size} bytes ({size/1024/1024:.2f} MB)")
            return final_path
        
        return None
        
    except Exception as e:
        print(f">>> API download failed: {str(e)}")
        # Fallback to yt-dlp
        return download_youtube_video_ytdlp(url, output_path)


def download_youtube_video_ytdlp(url, output_path):
    """
    Fallback: Download using yt-dlp with cookies and user-agent spoofing
    """
    print(f"\n>>> Fallback to yt-dlp: {url}")
    
    try:
        import yt_dlp
        
        ydl_opts = {
            'format': 'best[height<=720][ext=mp4]/best[ext=mp4]/best',
            'outtmpl': output_path,
            'quiet': False,
            'no_warnings': False,
            # Spoof user agent to look like a browser
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            # Add referer
            'referer': 'https://www.youtube.com/',
            'socket_timeout': 30,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print(">>> Extracting video info...")
            info = ydl.extract_info(url, download=True)
            print(f">>> Title: {info.get('title', 'Unknown')}")
        
        # Check for file
        possible_paths = [
            output_path,
            f"{output_path}.mp4",
            output_path.replace('.mp4', '') + '.mp4'
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                size = os.path.getsize(path)
                print(f">>> SUCCESS! File at: {path} ({size/1024/1024:.2f} MB)")
                return path
        
        print(">>> ERROR: File not found after download")
        return None
            
    except Exception as e:
        print(f">>> yt-dlp failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return None


def download_youtube_audio(url, output_path):
    """Download audio from YouTube video"""
    print(f"\n>>> Downloading audio: {url}")
    
    try:
        import yt_dlp
        
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': output_path,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'quiet': False,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        mp3_path = output_path + '.mp3'
        if os.path.exists(mp3_path):
            print(f">>> Audio downloaded: {mp3_path}")
            return mp3_path
        
        return None
            
    except Exception as e:
        print(f">>> Audio download failed: {str(e)}")
        return None


def get_trending_song():
    """Get trending music video URL"""
    print("\n>>> Getting trending song...")
    
    if not YOUTUBE_API_KEY:
        print(">>> No API key, using fallback")
        return "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    try:
        params = {
            'part': 'snippet',
            'chart': 'mostPopular',
            'videoCategoryId': '10',
            'maxResults': 1,
            'regionCode': 'US',
            'key': YOUTUBE_API_KEY
        }
        
        url = "https://www.googleapis.com/youtube/v3/videos"
        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        if data.get('items'):
            video_id = data['items'][0]['id']
            song_url = f"https://www.youtube.com/watch?v={video_id}"
            print(f">>> Trending song: {song_url}")
            return song_url
            
    except Exception as e:
        print(f">>> Error: {e}")
    
    return "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def process_video(input_path, output_path):
    """Process video: remove audio and add new music"""
    print(f"\n>>> Processing video: {input_path}")
    
    try:
        from moviepy.editor import VideoFileClip, AudioFileClip, CompositeAudioClip
    except ImportError as e:
        print(f">>> ERROR: moviepy not available: {e}")
        return False

    try:
        print(">>> Loading video...")
        video = VideoFileClip(input_path)
        print(f">>> Duration: {video.duration:.2f}s")

        song_url = get_trending_song()
        audio_base = os.path.join(TEMP_DIR, f'song_{int(time.time())}')
        audio_file = download_youtube_audio(song_url, audio_base)

        if not audio_file:
            print(">>> Creating silent video")
            video_no_audio = video.without_audio()
            video_no_audio.write_videofile(
                output_path,
                codec='libx264',
                audio_codec='aac',
                preset='ultrafast',
                threads=2
            )
            video_no_audio.close()
        else:
            print(">>> Adding new audio...")
            new_audio = AudioFileClip(audio_file)
            
            if video.duration > new_audio.duration:
                loops = int(video.duration / new_audio.duration) + 1
                print(f">>> Looping audio {loops} times")
                new_audio = CompositeAudioClip([
                    new_audio.set_start(i * new_audio.duration) 
                    for i in range(loops)
                ])
            
            new_audio = new_audio.subclip(0, video.duration)
            video_no_audio = video.without_audio()
            final_video = video_no_audio.set_audio(new_audio)
            
            print(">>> Writing final video...")
            final_video.write_videofile(
                output_path,
                codec='libx264',
                audio_codec='aac',
                preset='ultrafast',
                threads=2
            )
            
            new_audio.close()
            final_video.close()
            video_no_audio.close()
            
            if os.path.exists(audio_file):
                os.remove(audio_file)

        video.close()
        print(f">>> Processing complete: {output_path}")
        return True

    except Exception as e:
        print(f">>> ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


@app.route('/', methods=['GET'])
def home():
    return jsonify({
        'service': 'YouTube Video Automation',
        'status': 'running',
        'version': '2.0 - API-based',
        'endpoints': ['/health', '/download', '/process-video', '/get-file/<filename>']
    })


@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'healthy',
        'temp_dir': TEMP_DIR,
        'youtube_api': bool(YOUTUBE_API_KEY),
        'download_method': 'cobalt.tools API + yt-dlp fallback'
    })


@app.route('/download', methods=['POST'])
def download_endpoint():
    print("\n=== /download ENDPOINT ===")
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data'}), 400
            
        video_url = data.get('videoUrl')
        if not video_url:
            return jsonify({'error': 'No videoUrl'}), 400

        print(f"Request: {video_url}")
        
        timestamp = int(time.time())
        output_base = os.path.join(TEMP_DIR, f'video_{timestamp}')
        
        # Use API-based download (bypasses YouTube blocks)
        downloaded_path = download_youtube_video_via_api(video_url, output_base)

        if downloaded_path and os.path.exists(downloaded_path):
            filename = os.path.basename(downloaded_path)
            size = os.path.getsize(downloaded_path)
            
            print(f"=== SUCCESS ===")
            print(f"File: {filename}, Size: {size/1024/1024:.2f} MB")
            
            return jsonify({
                'success': True,
                'fileUrl': f'/get-file/{filename}',
                'filename': filename,
                'size': size
            })
        else:
            print("=== FAILED ===")
            return jsonify({'error': 'Download failed'}), 500

    except Exception as e:
        print(f"=== EXCEPTION: {str(e)} ===")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/process-video', methods=['POST'])
def process_endpoint():
    print("\n=== /process-video ENDPOINT ===")
    input_path = None
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data'}), 400
            
        video_url = data.get('videoUrl')
        if not video_url:
            return jsonify({'error': 'No videoUrl'}), 400

        print(f"Request: {video_url}")
        
        timestamp = int(time.time())
        input_path = os.path.join(TEMP_DIR, f'input_{timestamp}.mp4')
        
        print(f">>> Downloading input...")
        response = requests.get(video_url, stream=True, timeout=300)
        response.raise_for_status()
        
        with open(input_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        size = os.path.getsize(input_path)
        print(f">>> Input downloaded: {size/1024/1024:.2f} MB")

        output_path = os.path.join(TEMP_DIR, f'output_{timestamp}.mp4')
        success = process_video(input_path, output_path)

        if success and os.path.exists(output_path):
            filename = os.path.basename(output_path)
            size = os.path.getsize(output_path)
            
            print(f"=== SUCCESS ===")
            
            return jsonify({
                'success': True,
                'processedFileUrl': f'/get-file/{filename}',
                'filename': filename,
                'size': size
            })
        else:
            return jsonify({'error': 'Processing failed'}), 500

    except Exception as e:
        print(f"=== EXCEPTION: {str(e)} ===")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        if input_path and os.path.exists(input_path):
            try:
                os.remove(input_path)
            except:
                pass


@app.route('/get-file/<filename>', methods=['GET'])
def get_file_endpoint(filename):
    print(f"\n=== /get-file/{filename} ===")
    
    file_path = os.path.join(TEMP_DIR, filename)
    
    if os.path.exists(file_path):
        size = os.path.getsize(file_path)
        print(f"Serving: {size/1024/1024:.2f} MB")
        return send_file(
            file_path,
            mimetype='video/mp4',
            as_attachment=True,
            download_name=filename
        )
    
    print("File not found!")
    return jsonify({'error': 'File not found'}), 404


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"\n=== STARTING SERVER ON PORT {port} ===\n")
    app.run(host='0.0.0.0', port=port, debug=False)
