from flask import Flask, request, jsonify, send_file
import yt_dlp
import requests
import os
import tempfile
import time

app = Flask(__name__)

# Configuration
YOUTUBE_API_KEY = os.environ.get('YOUTUBE_API_KEY', '')
TEMP_DIR = tempfile.gettempdir()

print(f"=== SERVER STARTING ===")
print(f"TEMP_DIR: {TEMP_DIR}")
print(f"YouTube API Key: {'SET' if YOUTUBE_API_KEY else 'NOT SET'}")


def download_youtube_video(url, output_path):
    """Download video from YouTube - IMPROVED VERSION"""
    print(f"\n>>> Downloading video from: {url}")
    print(f">>> Output path: {output_path}")
    
    ydl_opts = {
        'format': 'best[height<=720][ext=mp4]/best[ext=mp4]/best',
        'outtmpl': output_path,
        'quiet': False,
        'no_warnings': False,
        'extract_flat': False,
        'socket_timeout': 30,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print(">>> Extracting video info...")
            info = ydl.extract_info(url, download=True)
            video_title = info.get('title', 'Unknown')
            print(f">>> Video title: {video_title}")
            print(f">>> Download completed!")
        
        # Check multiple possible filenames
        possible_paths = [
            output_path,
            f"{output_path}.mp4",
            output_path.replace('.mp4', '') + '.mp4'
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                size = os.path.getsize(path)
                print(f">>> SUCCESS! File found at: {path}")
                print(f">>> File size: {size} bytes ({size/1024/1024:.2f} MB)")
                return path
        
        print(f">>> ERROR: Video file not found in any expected location")
        print(f">>> Checked paths: {possible_paths}")
        return None
            
    except Exception as e:
        print(f">>> ERROR downloading video: {str(e)}")
        import traceback
        traceback.print_exc()
        return None


def download_youtube_audio(url, output_path):
    """Download audio from YouTube video"""
    print(f"\n>>> Downloading audio from: {url}")
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': output_path,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'quiet': False,
        'no_warnings': False,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        mp3_path = output_path + '.mp3'
        if os.path.exists(mp3_path):
            print(f">>> Audio downloaded: {mp3_path}")
            return mp3_path
        
        print(f">>> Audio file not found at: {mp3_path}")
        return None
            
    except Exception as e:
        print(f">>> ERROR downloading audio: {str(e)}")
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
            print(f">>> Found trending song: {song_url}")
            return song_url
            
    except Exception as e:
        print(f">>> Error getting trending song: {e}")
    
    return "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def process_video(input_path, output_path):
    """Process video: remove original audio and add new music"""
    print(f"\n>>> Processing video: {input_path}")
    
    try:
        from moviepy.editor import VideoFileClip, AudioFileClip, CompositeAudioClip
    except ImportError as e:
        print(f">>> ERROR: moviepy not available: {e}")
        return False

    try:
        print(">>> Loading video...")
        video = VideoFileClip(input_path)
        print(f">>> Video duration: {video.duration:.2f} seconds")

        # Get trending song
        song_url = get_trending_song()
        
        # Download audio
        audio_base = os.path.join(TEMP_DIR, f'song_{int(time.time())}')
        audio_file = download_youtube_audio(song_url, audio_base)

        if not audio_file:
            print(">>> Creating silent video (audio download failed)")
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
            print(">>> Adding new audio to video...")
            new_audio = AudioFileClip(audio_file)
            
            # Loop audio if needed
            if video.duration > new_audio.duration:
                loops = int(video.duration / new_audio.duration) + 1
                print(f">>> Looping audio {loops} times")
                new_audio = CompositeAudioClip([
                    new_audio.set_start(i * new_audio.duration) 
                    for i in range(loops)
                ])
            
            new_audio = new_audio.subclip(0, video.duration)
            
            # Create final video
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
            
            # Cleanup
            new_audio.close()
            final_video.close()
            video_no_audio.close()
            
            if os.path.exists(audio_file):
                os.remove(audio_file)

        video.close()
        print(f">>> Video processing complete: {output_path}")
        return True

    except Exception as e:
        print(f">>> ERROR processing video: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


@app.route('/', methods=['GET'])
def home():
    return jsonify({
        'service': 'YouTube Video Automation',
        'status': 'running',
        'endpoints': ['/health', '/download', '/process-video', '/get-file/<filename>']
    })


@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'healthy',
        'temp_dir': TEMP_DIR,
        'youtube_api': bool(YOUTUBE_API_KEY)
    })


@app.route('/download', methods=['POST'])
def download_endpoint():
    print("\n=== /download ENDPOINT CALLED ===")
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data'}), 400
            
        video_url = data.get('videoUrl')
        if not video_url:
            return jsonify({'error': 'No videoUrl in request'}), 400

        print(f"Request: {data}")
        
        # Download video
        timestamp = int(time.time())
        output_base = os.path.join(TEMP_DIR, f'video_{timestamp}')
        
        downloaded_path = download_youtube_video(video_url, output_base)

        if downloaded_path and os.path.exists(downloaded_path):
            filename = os.path.basename(downloaded_path)
            size = os.path.getsize(downloaded_path)
            
            print(f"=== SUCCESS ===")
            print(f"File: {filename}")
            print(f"Size: {size} bytes")
            
            return jsonify({
                'success': True,
                'fileUrl': f'/get-file/{filename}',
                'filename': filename,
                'size': size
            })
        else:
            print("=== FAILED: File not created ===")
            return jsonify({'error': 'Failed to download video'}), 500

    except Exception as e:
        print(f"=== EXCEPTION ===")
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/process-video', methods=['POST'])
def process_endpoint():
    print("\n=== /process-video ENDPOINT CALLED ===")
    input_path = None
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data'}), 400
            
        video_url = data.get('videoUrl')
        if not video_url:
            return jsonify({'error': 'No videoUrl in request'}), 400

        print(f"Request: {data}")
        
        # Download input video
        timestamp = int(time.time())
        input_path = os.path.join(TEMP_DIR, f'input_{timestamp}.mp4')
        
        print(f">>> Downloading input from: {video_url}")
        response = requests.get(video_url, stream=True, timeout=300)
        response.raise_for_status()
        
        with open(input_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        size = os.path.getsize(input_path)
        print(f">>> Input downloaded: {size} bytes")

        # Process video
        output_path = os.path.join(TEMP_DIR, f'output_{timestamp}.mp4')
        success = process_video(input_path, output_path)

        if success and os.path.exists(output_path):
            filename = os.path.basename(output_path)
            size = os.path.getsize(output_path)
            
            print(f"=== SUCCESS ===")
            print(f"File: {filename}")
            print(f"Size: {size} bytes")
            
            return jsonify({
                'success': True,
                'processedFileUrl': f'/get-file/{filename}',
                'filename': filename,
                'size': size
            })
        else:
            print("=== FAILED: Processing failed ===")
            return jsonify({'error': 'Video processing failed'}), 500

    except Exception as e:
        print(f"=== EXCEPTION ===")
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        if input_path and os.path.exists(input_path):
            try:
                os.remove(input_path)
                print(f">>> Cleaned up: {input_path}")
            except:
                pass


@app.route('/get-file/<filename>', methods=['GET'])
def get_file_endpoint(filename):
    print(f"\n=== /get-file/{filename} CALLED ===")
    
    file_path = os.path.join(TEMP_DIR, filename)
    print(f"Looking for: {file_path}")
    
    if os.path.exists(file_path):
        size = os.path.getsize(file_path)
        print(f"File found: {size} bytes")
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
